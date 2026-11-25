"""Ikki tomonlama sharhlar, xabar almashish va bildirishnomalar."""
import json
import sqlite3

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.routing import Route

from ..db import get_db, one, rows
from ..i18n import tr
from ..schemas import MessageIn, ReplyIn, ReviewIn
from ..security import message_limiter, require
from ..utils import car_title, notify, ok, parse_body, path_int, q_int
from .bookings import maintain


# ---------------- Sharhlar ----------------
@require()
async def create_review(request: Request):
    """Ijarachi avtomobilni (kind=car), owner ijarachini (kind=renter) baholaydi. Faqat yakunlangan bron, har tomon 1 marta."""
    data = await parse_body(request, ReviewIn)
    user = request.state.user
    with get_db() as db:
        maintain(db)
        b = one(db.execute("SELECT b.*, c.owner_id, c.brand, c.model, c.year FROM bookings b JOIN cars c ON c.id = b.car_id "
                           "WHERE b.id = ?", (data.booking_id,)))
        if not b or user["id"] not in (b["renter_id"], b["owner_id"]):
            raise HTTPException(404, tr("Bron topilmadi"))
        if b["status"] != "completed":
            raise HTTPException(400, tr("Sharhni faqat ijara yakunlangandan keyin qoldirish mumkin"))
        if user["id"] == b["renter_id"]:
            kind, target = "car", b["owner_id"]
        else:
            kind, target = "renter", b["renter_id"]
        try:
            cur = db.execute("INSERT INTO reviews (booking_id, car_id, author_id, target_user_id, kind, rating, comment) "
                             "VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (b["id"], b["car_id"], user["id"], target, kind, data.rating, data.comment))
        except sqlite3.IntegrityError:
            raise HTTPException(409, tr("Bu ijara uchun sharh allaqachon qoldirilgan"))
        notify(db, target, "review_new", f"/car.html?id={b['car_id']}#reviews" if kind == "car" else "/dashboard.html",
               mode="owner" if kind == "car" else "renter", actor_id=user["id"], name=user["full_name"], car=car_title(b), rating=data.rating)
        review = one(db.execute("SELECT * FROM reviews WHERE id = ?", (cur.lastrowid,)))
    return ok(review, 201)


@require()
async def reply_review(request: Request):
    data = await parse_body(request, ReplyIn)
    rid = path_int(request)
    with get_db() as db:
        r = one(db.execute("SELECT r.*, c.owner_id FROM reviews r JOIN cars c ON c.id = r.car_id WHERE r.id = ? AND r.kind = 'car'",
                           (rid,)))
        if not r:
            raise HTTPException(404, tr("Sharh topilmadi"))
        if r["owner_id"] != request.state.user["id"]:
            raise HTTPException(403, tr("Faqat avtomobil egasi javob bera oladi"))
        db.execute("UPDATE reviews SET reply = ? WHERE id = ?", (data.reply, rid))
    return ok({"id": rid, "reply": data.reply})


@require()
async def my_car_reviews(request: Request):
    """Owner uchun: avtomobillariga qoldirilgan sharhlar (javob berish uchun)."""
    with get_db() as db:
        items = rows(db.execute(
            "SELECT r.id, r.rating, r.comment, r.reply, r.created_at, r.car_id, c.brand, c.model, c.year, u.full_name AS author "
            "FROM reviews r JOIN cars c ON c.id = r.car_id JOIN users u ON u.id = r.author_id "
            "WHERE c.owner_id = ? AND r.kind = 'car' ORDER BY r.id DESC LIMIT 100", (request.state.user["id"],)))
    return ok({"items": items})


async def latest_reviews(request: Request):
    """Bosh sahifadagi "Foydalanuvchilar fikrlari": faqat haqiqiy, yakunlangan ijaradan keyingi sharhlar."""
    with get_db() as db:
        items = rows(db.execute(
            "SELECT r.id, r.rating, r.comment, r.created_at, u.full_name AS author, c.id AS car_id, c.brand, c.model "
            "FROM reviews r JOIN users u ON u.id = r.author_id JOIN cars c ON c.id = r.car_id "
            "WHERE r.kind = 'car' AND r.rating >= 4 AND r.comment IS NOT NULL ORDER BY r.created_at DESC LIMIT 6"))
    return ok({"items": items})


# ---------------- Xabarlar ----------------
@require()
async def conversations(request: Request):
    me = request.state.user["id"]
    with get_db() as db:
        items = rows(db.execute(
            """
            WITH pairs AS (
                SELECT CASE WHEN sender_id = :me THEN receiver_id ELSE sender_id END AS other_id, MAX(id) AS last_id
                FROM messages WHERE sender_id = :me OR receiver_id = :me GROUP BY other_id
            )
            SELECT p.other_id, u.full_name AS other_name, u.avatar AS other_avatar,
                   (SELECT CASE WHEN c.owner_id = :me THEN 'owner' ELSE 'renter' END FROM messages mm JOIN cars c ON c.id = mm.car_id
                     WHERE ((mm.sender_id = :me AND mm.receiver_id = p.other_id) OR (mm.sender_id = p.other_id AND mm.receiver_id = :me))
                     ORDER BY mm.id DESC LIMIT 1) AS ctx,
                   m.body AS last_body, m.created_at AS last_at, m.sender_id = :me AS last_is_mine,
                   (SELECT COUNT(*) FROM messages x WHERE x.sender_id = p.other_id AND x.receiver_id = :me AND x.is_read = 0) AS unread
            FROM pairs p JOIN messages m ON m.id = p.last_id JOIN users u ON u.id = p.other_id
            ORDER BY p.last_id DESC
            """, {"me": me}))
    return ok({"items": items})


@require()
async def thread(request: Request):
    """Faqat ikki ishtirokchi o'z yozishmasini ko'radi: so'rov har doim joriy user bilan filtrlanadi."""
    me, other = request.state.user["id"], path_int(request, "user_id")
    after = q_int(request, "after", 0, lo=0)
    with get_db() as db:
        partner = one(db.execute("SELECT id, full_name FROM users WHERE id = ?", (other,)))
        if not partner:
            raise HTTPException(404, tr("Foydalanuvchi topilmadi"))
        items = rows(db.execute(
            """SELECT m.id, m.sender_id, m.receiver_id, m.body, m.is_read, m.created_at, m.car_id, m.kind, m.lat, m.lng,
                      c.brand || ' ' || c.model AS car_title
               FROM messages m LEFT JOIN cars c ON c.id = m.car_id
               WHERE ((m.sender_id = ? AND m.receiver_id = ?) OR (m.sender_id = ? AND m.receiver_id = ?)) AND m.id > ?
               ORDER BY m.id DESC LIMIT 200""", (me, other, other, me, after)))
        items.reverse()
        db.execute("UPDATE messages SET is_read = 1 WHERE sender_id = ? AND receiver_id = ? AND is_read = 0", (other, me))
    return ok({"partner": partner, "items": items})


@require()
async def send_message(request: Request):
    data = await parse_body(request, MessageIn)
    me = request.state.user
    if data.to_user_id == me["id"]:
        raise HTTPException(400, tr("O'zingizga xabar yubora olmaysiz"))
    if not message_limiter.hit(str(me["id"])):
        raise HTTPException(429, tr("Juda ko'p xabar. Biroz kuting"))
    with get_db() as db:
        to = one(db.execute("SELECT id, is_active FROM users WHERE id = ?", (data.to_user_id,)))
        if not to or not to["is_active"]:
            raise HTTPException(404, tr("Qabul qiluvchi topilmadi"))
        car_id = data.car_id
        if car_id and not db.execute("SELECT 1 FROM cars WHERE id = ?", (car_id,)).fetchone():
            car_id = None
        cur = db.execute("INSERT INTO messages (sender_id, receiver_id, car_id, body, kind, lat, lng) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (me["id"], to["id"], car_id, data.body, data.kind, data.lat, data.lng))
        car = one(db.execute("SELECT owner_id, brand, model FROM cars WHERE id = ?", (car_id,))) if car_id else None
        # Qabul qiluvchi uchun kontekst: mashina uniki bo'lsa — owner kabineti, boshqaniki bo'lsa — ijarachi kabineti
        mode = ("owner" if car["owner_id"] == to["id"] else "renter") if car else "any"
        link = f"/messages.html?user={me['id']}" + (f"&mode={mode}" if mode != "any" else "")
        db.execute("DELETE FROM notifications WHERE user_id = ? AND type = 'message' AND link = ? AND is_read = 0", (to["id"], link))
        notify(db, to["id"], "message", link, mode=mode, actor_id=me["id"], name=me["full_name"], preview=("📍 " if data.kind == "location" else "") + data.body[:80],
               car=f"{car['brand']} {car['model']}" if car else "")
        msg = one(db.execute("SELECT * FROM messages WHERE id = ?", (cur.lastrowid,)))
    return ok(msg, 201)


# ---------------- Shikoyatlar ----------------
REPORT_TARGETS = {"car": "SELECT id FROM cars WHERE id = ?", "review": "SELECT id FROM reviews WHERE id = ?",
                  "user": "SELECT id FROM users WHERE id = ?", "message": "SELECT id FROM messages WHERE id = ? AND receiver_id = ?"}


@require()
async def create_report(request: Request):
    from ..schemas import ReportIn
    data = await parse_body(request, ReportIn)
    me = request.state.user
    with get_db() as db:
        params = (data.target_id, me["id"]) if data.target_type == "message" else (data.target_id,)
        if not db.execute(REPORT_TARGETS[data.target_type], params).fetchone():
            raise HTTPException(404, tr("Shikoyat obyekti topilmadi"))
        if data.target_type == "user" and data.target_id == me["id"]:
            raise HTTPException(400, tr("Shikoyat obyekti topilmadi"))
        # Bitta obyekt ustidan bitta ochiq shikoyat (spamga qarshi)
        if db.execute("SELECT 1 FROM reports WHERE reporter_id = ? AND target_type = ? AND target_id = ? AND status = 'new'",
                      (me["id"], data.target_type, data.target_id)).fetchone():
            raise HTTPException(409, tr("Siz bu haqda allaqachon shikoyat yuborgansiz"))
        cur = db.execute("INSERT INTO reports (reporter_id, target_type, target_id, reason, comment) VALUES (?, ?, ?, ?, ?)",
                         (me["id"], data.target_type, data.target_id, data.reason, data.comment))
        for (aid,) in db.execute("SELECT id FROM users WHERE role = 'admin' AND is_active = 1").fetchall():
            notify(db, aid, "report_new", "/admin.html#reports", reason=data.reason)
    return ok({"id": cur.lastrowid}, 201)


# ---------------- Bildirishnomalar ----------------
@require()
async def notifications(request: Request):
    uid = request.state.user["id"]
    with get_db() as db:
        after = q_int(request, "after", 0, lo=0)
        items = rows(db.execute(
            """SELECT n.*, a.full_name AS actor_name, a.avatar AS actor_avatar FROM notifications n LEFT JOIN users a ON a.id = n.actor_id
               WHERE n.user_id = ? AND n.id > ? ORDER BY n.id DESC LIMIT 30""", (uid, after)))
        unread = db.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0", (uid,)).fetchone()[0]
    for n in items:
        n["params"] = json.loads(n["params"] or "{}")
    return ok({"items": items, "unread": unread})


@require()
async def read_all(request: Request):
    with get_db() as db:
        db.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (request.state.user["id"],))
    return ok()


@require()
async def read_one(request: Request):
    with get_db() as db:
        db.execute("UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?", (path_int(request), request.state.user["id"]))
    return ok()


routes = [
    Route("/api/reviews", create_review, methods=["POST"]),
    Route("/api/reviews/latest", latest_reviews, methods=["GET"]),
    Route("/api/reviews/{id:int}/reply", reply_review, methods=["POST"]),
    Route("/api/my/car-reviews", my_car_reviews, methods=["GET"]),
    Route("/api/messages", conversations, methods=["GET"]),
    Route("/api/messages", send_message, methods=["POST"]),
    Route("/api/messages/{user_id:int}", thread, methods=["GET"]),
    Route("/api/reports", create_report, methods=["POST"]),
    Route("/api/notifications", notifications, methods=["GET"]),
    Route("/api/notifications/read-all", read_all, methods=["POST"]),
    Route("/api/notifications/{id:int}/read", read_one, methods=["POST"]),
]
