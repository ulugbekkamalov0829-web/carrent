"""Admin: bitta foydalanuvchining to'liq sahifasi va uni boshqarish.

Shikoyat, nizo, to'lov yoki hisobotdan shu sahifaga o'tiladi. Admin bu yerda ko'radi:
profil va tasdiqlanganlik, ijarachi/owner sifatidagi faoliyati va pullari, mashinalari, bronlari, to'lovlari,
unga va u yozgan shikoyatlar, nizolar, sharhlar, faol sessiyalar, admin eslatmalari va audit tarixi.
Amallar: bloklash/blokdan chiqarish (sabab bilan), ogohlantirish (foydalanuvchiga bildirishnoma boradi), ichki eslatma,
email/telefonni tasdiqlash yoki bekor qilish, barcha qurilmalardan chiqarish, barcha e'lonlarni yashirish/qaytarish,
bronni admin sifatida bekor qilish (siyosat bo'yicha yoki to'liq qaytarish bilan). Har bir amal audit jurnaliga yoziladi.
"""
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.routing import Route

from ..db import get_db, one, rows, transaction
from ..i18n import tr
from ..schemas import AdminBookingCancel, AdminUserAction
from ..security import require, revoke_user_sessions
from ..utils import audit, car_title, notify, ok, parse_body, path_int
from .bookings import BOOKING_SELECT, maintain

DONE = "('approved', 'completed')"
COVER = "(SELECT path FROM car_images i WHERE i.car_id = c.id ORDER BY position, id LIMIT 1)"
COMPLAINTS_AGAINST = """(
    (r.target_type = 'user' AND r.target_id = :uid)
 OR (r.target_type = 'car' AND r.target_id IN (SELECT id FROM cars WHERE owner_id = :uid))
 OR (r.target_type = 'message' AND r.target_id IN (SELECT id FROM messages WHERE sender_id = :uid))
 OR (r.target_type = 'review' AND r.target_id IN (SELECT id FROM reviews WHERE author_id = :uid)))"""


def _statuses(db, where: str, params) -> dict:
    out = {s: 0 for s in ("pending", "approved", "rejected", "cancelled", "completed")}
    for s, n in db.execute(f"SELECT b.status, COUNT(*) FROM bookings b JOIN cars c ON c.id = b.car_id WHERE {where} GROUP BY b.status", params):
        out[s] = n
    return out


def report_target_user(db, target_type: str, target_id: int) -> int | None:
    """Shikoyat aynan kim ustidan: e'lon egasi, xabar yuboruvchi, sharh muallifi yoki foydalanuvchining o'zi."""
    sql = {"user": "SELECT id FROM users WHERE id = ?", "car": "SELECT owner_id FROM cars WHERE id = ?",
           "message": "SELECT sender_id FROM messages WHERE id = ?", "review": "SELECT author_id FROM reviews WHERE id = ?"}.get(target_type)
    r = db.execute(sql, (target_id,)).fetchone() if sql else None
    return r[0] if r else None


@require("admin")
async def admin_user_detail(request: Request):
    uid = path_int(request)
    with get_db() as db:
        maintain(db)
        u = one(db.execute("""SELECT id, full_name, email, phone, avatar, role, is_active, created_at, region, district, lang, active_mode,
                                     email_verified, phone_verified, deleted_at, marketing_ok,
                                     (SELECT MAX(last_seen) FROM sessions s WHERE s.user_id = users.id) AS last_seen
                              FROM users WHERE id = ?""", (uid,)))
        if not u:
            raise HTTPException(404, tr("Foydalanuvchi topilmadi"))
        # Ijarachi sifatida
        rs = db.execute(f"SELECT COUNT(*), COALESCE(SUM(total_price), 0), COALESCE(SUM(days), 0) FROM bookings WHERE renter_id = ? AND status IN {DONE}",
                        (uid,)).fetchone()
        r_rating = one(db.execute("SELECT ROUND(AVG(rating), 1) AS avg, COUNT(*) AS cnt FROM reviews WHERE target_user_id = ? AND kind = 'renter'", (uid,)))
        renter = {"statuses": _statuses(db, "b.renter_id = ?", (uid,)), "trips": rs[0], "spent": rs[1], "days": rs[2],
                  "rating": r_rating["avg"], "rating_cnt": r_rating["cnt"]}
        # Owner sifatida
        cars = rows(db.execute(
            f"""SELECT c.id, c.brand, c.model, c.year, c.city, c.district, c.price_per_day, c.is_active, c.is_approved, c.views, c.created_at,
                       {COVER} AS cover,
                       (SELECT COUNT(*) FROM bookings b WHERE b.car_id = c.id AND b.status IN {DONE}) AS trips,
                       (SELECT ROUND(AVG(rating), 1) FROM reviews r WHERE r.car_id = c.id AND r.kind = 'car') AS rating
                FROM cars c WHERE c.owner_id = ? ORDER BY c.id DESC""", (uid,)))
        owner = None
        if cars:
            om = db.execute(f"""SELECT COUNT(*), COALESCE(SUM(b.total_price), 0), COALESCE(SUM(b.commission), 0), COALESCE(SUM(b.owner_payout), 0)
                                FROM bookings b JOIN cars c ON c.id = b.car_id WHERE c.owner_id = ? AND b.status IN {DONE}""", (uid,)).fetchone()
            o_rating = one(db.execute("SELECT ROUND(AVG(r.rating), 1) AS avg, COUNT(*) AS cnt FROM reviews r JOIN cars c ON c.id = r.car_id "
                                      "WHERE c.owner_id = ? AND r.kind = 'car'", (uid,)))
            from .payments import owner_balance
            owner = {"statuses": _statuses(db, "c.owner_id = ?", (uid,)), "trips": om[0], "gross": om[1], "commission": om[2], "payout": om[3],
                     "rating": o_rating["avg"], "rating_cnt": o_rating["cnt"], "cars_total": len(cars),
                     "cars_active": sum(1 for c in cars if c["is_active"] and c["is_approved"]), "balance": owner_balance(db, uid)}
        bookings = rows(db.execute(BOOKING_SELECT + " WHERE b.renter_id = ? OR c.owner_id = ? ORDER BY b.id DESC LIMIT 40", (uid, uid)))
        payments = rows(db.execute(
            f"""SELECT p.id, p.provider, p.amount, p.status, p.refund_amount, p.paid_at, p.created_at, b.id AS booking_id,
                       c.brand, c.model, c.year, p.user_id, ru.full_name AS renter_name, c.owner_id
                FROM payments p JOIN bookings b ON b.id = p.booking_id JOIN cars c ON c.id = b.car_id JOIN users ru ON ru.id = p.user_id
                WHERE (p.user_id = ? OR c.owner_id = ?) AND p.status NOT IN ('created') ORDER BY p.id DESC LIMIT 30""", (uid, uid)))
        against = rows(db.execute(
            f"""SELECT r.*, u.full_name AS reporter_name FROM reports r JOIN users u ON u.id = r.reporter_id
                WHERE {COMPLAINTS_AGAINST} ORDER BY (r.status = 'new') DESC, r.id DESC LIMIT 50""", {"uid": uid}))
        by_user = rows(db.execute("SELECT r.* FROM reports r WHERE r.reporter_id = ? ORDER BY r.id DESC LIMIT 30", (uid,)))
        from .dashboard import report_label
        for r in against + by_user:
            report_label(db, r)
        disputes = rows(db.execute(
            """SELECT d.id, d.booking_id, d.type, d.status, d.amount, d.outcome, d.created_at, d.opened_by, d.against_id,
                      a.full_name AS opener_name, x.full_name AS against_name, c.brand, c.model, c.year
               FROM disputes d JOIN users a ON a.id = d.opened_by JOIN users x ON x.id = d.against_id
               JOIN bookings b ON b.id = d.booking_id JOIN cars c ON c.id = b.car_id
               WHERE d.opened_by = ? OR d.against_id = ? ORDER BY d.id DESC LIMIT 30""", (uid, uid)))
        reviews = rows(db.execute(
            """SELECT r.id, r.kind, r.rating, r.comment, r.created_at, r.author_id, a.full_name AS author_name,
                      r.target_user_id, c.id AS car_id, c.brand, c.model, c.year
               FROM reviews r JOIN users a ON a.id = r.author_id JOIN cars c ON c.id = r.car_id
               WHERE r.target_user_id = ? OR r.author_id = ? ORDER BY r.id DESC LIMIT 40""", (uid, uid)))
        sessions = rows(db.execute("SELECT ip, user_agent, created_at, last_seen FROM sessions WHERE user_id = ? AND revoked_at IS NULL "
                                   "ORDER BY last_seen DESC LIMIT 10", (uid,)))
        notes = rows(db.execute("""SELECT n.id, n.kind, n.body, n.created_at, a.full_name AS author_name FROM admin_notes n
                                   LEFT JOIN users a ON a.id = n.author_id WHERE n.user_id = ? ORDER BY n.id DESC LIMIT 50""", (uid,)))
        history = rows(db.execute("""SELECT a.action, a.details, a.created_at, a.target_type, a.target_id, x.full_name AS actor_name
                                     FROM audit_logs a LEFT JOIN users x ON x.id = a.actor_id
                                     WHERE (a.target_type = 'user' AND a.target_id = ?) OR a.actor_id = ? ORDER BY a.id DESC LIMIT 40""", (uid, uid)))
        counts = {"messages": db.execute("SELECT COUNT(*) FROM messages WHERE sender_id = ?", (uid,)).fetchone()[0],
                  "complaints_new": sum(1 for r in against if r["status"] == "new"), "complaints": len(against),
                  "warnings": sum(1 for n in notes if n["kind"] == "warning"),
                  "disputes_open": sum(1 for d in disputes if d["status"] in ("open", "in_review"))}
        # Xavf belgilari: admin e'tiborini tortadigan oddiy qoidalar
        flags = []
        if counts["complaints_new"]:
            flags.append({"code": "complaints", "n": counts["complaints_new"]})
        if counts["disputes_open"]:
            flags.append({"code": "disputes", "n": counts["disputes_open"]})
        if renter["statuses"]["cancelled"] >= 3 and renter["statuses"]["cancelled"] > renter["trips"]:
            flags.append({"code": "cancels", "n": renter["statuses"]["cancelled"]})
        if renter["rating"] is not None and renter["rating"] < 3:
            flags.append({"code": "low_renter_rating", "n": renter["rating"]})
        if owner and owner["rating"] is not None and owner["rating"] < 3:
            flags.append({"code": "low_owner_rating", "n": owner["rating"]})
        if owner and owner["balance"]["fee_owed"]:
            flags.append({"code": "fee_owed", "n": owner["balance"]["fee_owed"]})
        if counts["warnings"] >= 2:
            flags.append({"code": "warnings", "n": counts["warnings"]})
        if not u["email_verified"] and not u["phone_verified"]:
            flags.append({"code": "unverified", "n": 0})
    return ok({"user": u, "renter": renter, "owner": owner, "cars": cars, "bookings": bookings, "payments": payments,
               "complaints_against": against, "complaints_by": by_user, "disputes": disputes, "reviews": reviews,
               "sessions": sessions, "notes": notes, "history": history, "counts": counts, "flags": flags})


@require("admin")
async def admin_user_action(request: Request):
    uid = path_int(request)
    data = await parse_body(request, AdminUserAction)
    me = request.state.user["id"]
    reason = (data.reason or "").strip()
    with get_db() as db:
        with transaction(db):
            u = one(db.execute("SELECT id, role, email, full_name, is_active FROM users WHERE id = ?", (uid,)))
            if not u:
                raise HTTPException(404, tr("Foydalanuvchi topilmadi"))
            if data.action not in ("note",) and (uid == me or u["role"] == "admin"):
                raise HTTPException(400, tr("Administrator akkauntiga bu amalni qo'llab bo'lmaydi"))
            a = data.action
            note = lambda kind, body: db.execute("INSERT INTO admin_notes (user_id, author_id, kind, body) VALUES (?, ?, ?, ?)",
                                                 (uid, me, kind, body))
            if a == "block":
                db.execute("UPDATE users SET is_active = 0 WHERE id = ?", (uid,))
                revoke_user_sessions(db, uid)
                note("block", reason)
            elif a == "unblock":
                db.execute("UPDATE users SET is_active = 1 WHERE id = ?", (uid,))
                note("unblock", reason or "—")
            elif a == "warn":
                note("warning", reason)
                notify(db, uid, "admin_warning", "/settings.html", mode="any", text=reason)
            elif a == "note":
                note("note", reason)
            elif a in ("verify_email", "unverify_email", "verify_phone", "unverify_phone"):
                col = "email_verified" if a.endswith("email") else "phone_verified"
                db.execute(f"UPDATE users SET {col} = ? WHERE id = ?", (int(a.startswith("verify")), uid))
            elif a == "logout_all":
                revoke_user_sessions(db, uid)
            elif a in ("hide_cars", "restore_cars"):
                hide = a == "hide_cars"
                n = db.execute("UPDATE cars SET is_approved = ? WHERE owner_id = ?", (0 if hide else 1, uid)).rowcount
                if n:
                    notify(db, uid, "cars_hidden_admin" if hide else "cars_restored_admin", "/dashboard.html?mode=owner#cars",
                           mode="owner", n=n, text=reason or "")
                if reason:
                    note("note", f"[{a}] {reason}")
            audit(db, request, "admin_" + a, "user", uid, email=u["email"], reason=reason[:200] or None)
    return ok({"id": uid, "action": data.action})


@require("admin")
async def admin_cancel_booking(request: Request):
    """Admin bronni bekor qiladi (masalan, firibgarlik yoki nizo natijasida). Onlayn to'langan bo'lsa —
    siyosat bo'yicha yoki to'liq qaytariladi. Ikkala tomonga sababi bilan bildirishnoma boradi."""
    bid = path_int(request)
    data = await parse_body(request, AdminBookingCancel)
    with get_db() as db:
        with transaction(db):
            b = one(db.execute(BOOKING_SELECT + " WHERE b.id = ?", (bid,)))
            if not b:
                raise HTTPException(404, tr("Bron topilmadi"))
            if b["status"] not in ("pending", "approved"):
                raise HTTPException(400, tr("Bu bronni bekor qilib bo'lmaydi"))
            db.execute("UPDATE bookings SET status = 'cancelled', updated_at = datetime('now') WHERE id = ?", (bid,))
            refund = None
            p = one(db.execute("SELECT * FROM payments WHERE booking_id = ? AND status = 'paid'", (bid,)))
            if p and data.full_refund:
                status = "refunded" if p["provider"] == "test" else "refund_pending"
                db.execute("UPDATE payments SET status = ?, refund_amount = amount, kept_commission = 0, kept_payout = 0, "
                           "cancelled_at = datetime('now') WHERE id = ?", (status, p["id"]))
                db.execute("UPDATE bookings SET payment_status = ? WHERE id = ?", (status, bid))
                notify(db, p["user_id"], "payment_refunded" if status == "refunded" else "payment_refund_pending",
                       f"/receipt.html?payment={p['id']}", total=p["amount"])
                refund = {"refund": p["amount"], "status": status}
            elif p:
                from .payments import refund_for_booking
                refund = refund_for_booking(db, b)
            for to, mode in ((b["renter_id"], "renter"), (b["owner_id"], "owner")):
                notify(db, to, "booking_cancelled_admin", f"/dashboard.html?mode={mode}#bookings", mode=mode,
                       car=car_title(b), start=b["start_date"], end=b["end_date"], text=data.reason)
            audit(db, request, "admin_booking_cancelled", "booking", bid, reason=data.reason[:200], full_refund=data.full_refund)
    return ok({"id": bid, "refund": refund})


routes = [
    Route("/api/admin/users/{id:int}", admin_user_detail, methods=["GET"]),
    Route("/api/admin/users/{id:int}/action", admin_user_action, methods=["POST"]),
    Route("/api/admin/bookings/{id:int}/cancel", admin_cancel_booking, methods=["POST"]),
]
