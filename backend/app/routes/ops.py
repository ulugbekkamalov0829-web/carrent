"""Foydalanuvchilar o'rtasidagi nizolar (admin hal qiladi) va admin uchun SMS/email kanallari paneli.

Nizo hayot sikli:  open --(admin oladi)--> in_review --(qaror)--> resolved | rejected
                   open/in_review --(murojaatchi kelishib oldi)--> cancelled
Ikkinchi tomon o'z javobini yozadi; admin chat orqali ikkalasi bilan gaplashadi va izohli qaror chiqaradi.
"""
import hmac

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .. import channels
from ..config import settings
from ..db import get_db, one, rows, transaction
from ..i18n import tr
from ..schemas import ChannelTestIn, DisputeIn, DisputeReplyIn, DisputeResolveIn
from ..security import normalize_phone, require, revoke_user_sessions
from ..utils import audit, car_title, notify, ok, parse_body, path_int, q_str, today

DISPUTE_WINDOW_DAYS = 30          # ijara tugaganidan keyin necha kun ichida nizo ochish mumkin
ACTIVE = ("open", "in_review")

DISPUTE_SELECT = """
    SELECT d.*, b.start_date, b.end_date, b.total_price, b.deposit, b.status AS booking_status, b.payment_status, b.car_id,
           b.renter_id, c.owner_id, c.brand, c.model, c.year,
           op.full_name AS opener_name, ag.full_name AS against_name, rs.full_name AS resolver_name
    FROM disputes d JOIN bookings b ON b.id = d.booking_id JOIN cars c ON c.id = b.car_id
    JOIN users op ON op.id = d.opened_by JOIN users ag ON ag.id = d.against_id
    LEFT JOIN users rs ON rs.id = d.resolved_by
"""


def _admins(db) -> list[int]:
    return [r[0] for r in db.execute("SELECT id FROM users WHERE role = 'admin' AND is_active = 1")]


def _load(db, did: int) -> dict:
    d = one(db.execute(DISPUTE_SELECT + " WHERE d.id = ?", (did,)))
    if not d:
        raise HTTPException(404, tr("Nizo topilmadi"))
    return d


# ---------------- Foydalanuvchi ----------------
@require("user")
async def open_dispute(request: Request):
    data = await parse_body(request, DisputeIn)
    me = request.state.user
    with get_db() as db:
        with transaction(db, immediate=True):
            b = one(db.execute("SELECT b.*, c.owner_id, c.brand, c.model, c.year FROM bookings b JOIN cars c ON c.id = b.car_id "
                               "WHERE b.id = ?", (data.booking_id,)))
            if not b or me["id"] not in (b["renter_id"], b["owner_id"]):
                raise HTTPException(404, tr("Bron topilmadi"))
            if b["status"] not in ("approved", "completed", "cancelled"):
                raise HTTPException(400, tr("Bu bron bo'yicha nizo ochib bo'lmaydi"))
            from datetime import date, timedelta
            if date.fromisoformat(b["end_date"]) + timedelta(days=DISPUTE_WINDOW_DAYS) < today():
                raise HTTPException(400, tr("Nizo ijara tugaganidan keyin {n} kun ichida ochiladi", n=DISPUTE_WINDOW_DAYS))
            if db.execute("SELECT 1 FROM disputes WHERE booking_id = ? AND status IN ('open', 'in_review')", (b["id"],)).fetchone():
                raise HTTPException(409, tr("Bu bron bo'yicha ochiq nizo bor"))
            against = b["owner_id"] if me["id"] == b["renter_id"] else b["renter_id"]
            cur = db.execute("INSERT INTO disputes (booking_id, opened_by, against_id, type, description, amount) VALUES (?, ?, ?, ?, ?, ?)",
                             (b["id"], me["id"], against, data.type, data.description, data.amount))
            notify(db, against, "dispute_opened", "/dashboard.html#disputes", mode="owner" if against == b["owner_id"] else "renter",
                   actor_id=me["id"], name=me["full_name"], car=car_title(b))
            for a in _admins(db):
                notify(db, a, "dispute_new_admin", "/admin.html#disputes", name=me["full_name"], car=car_title(b))
        return ok(_load(db, cur.lastrowid), 201)


@require()
async def my_disputes(request: Request):
    uid = request.state.user["id"]
    with get_db() as db:
        items = rows(db.execute(DISPUTE_SELECT + " WHERE d.opened_by = ? OR d.against_id = ? ORDER BY (d.status IN ('open', 'in_review')) DESC, d.id DESC",
                                (uid, uid)))
    return ok({"items": items})


@require()
async def reply_dispute(request: Request):
    did, me = path_int(request), request.state.user
    data = await parse_body(request, DisputeReplyIn)
    with get_db() as db:
        d = _load(db, did)
        if d["against_id"] != me["id"]:
            raise HTTPException(403, tr("Javobni faqat ikkinchi tomon yozadi"))
        if d["status"] not in ACTIVE:
            raise HTTPException(400, tr("Nizo yopilgan"))
        db.execute("UPDATE disputes SET response = ?, response_at = datetime('now') WHERE id = ?", (data.text, did))
        notify(db, d["opened_by"], "dispute_reply", "/dashboard.html#disputes", name=me["full_name"], car=car_title(d))
        for a in _admins(db):
            notify(db, a, "dispute_reply", "/admin.html#disputes", name=me["full_name"], car=car_title(d))
        return ok(_load(db, did))


@require()
async def withdraw_dispute(request: Request):
    did, me = path_int(request), request.state.user
    with get_db() as db:
        d = _load(db, did)
        if d["opened_by"] != me["id"]:
            raise HTTPException(403, tr("Nizoni faqat uni ochgan foydalanuvchi qaytarib oladi"))
        if d["status"] not in ACTIVE:
            raise HTTPException(400, tr("Nizo yopilgan"))
        db.execute("UPDATE disputes SET status = 'cancelled', resolved_at = datetime('now') WHERE id = ?", (did,))
        return ok(_load(db, did))


# ---------------- Admin ----------------
@require("admin")
async def admin_disputes(request: Request):
    status = q_str(request, "status") or "active"
    sql, params = DISPUTE_SELECT, []
    if status == "active":
        sql += " WHERE d.status IN ('open', 'in_review')"
    elif status != "all":
        sql += " WHERE d.status = ?"; params.append(status)
    with get_db() as db:
        items = rows(db.execute(sql + " ORDER BY (d.status = 'open') DESC, d.id DESC LIMIT 300", params))
        counts = dict(db.execute("SELECT status, COUNT(*) FROM disputes GROUP BY status").fetchall())
    return ok({"items": items, "counts": counts})


@require("admin")
async def admin_take_dispute(request: Request):
    did = path_int(request)
    with get_db() as db:
        d = _load(db, did)
        if d["status"] != "open":
            raise HTTPException(400, tr("Nizo allaqachon ko'rib chiqilmoqda yoki yopilgan"))
        db.execute("UPDATE disputes SET status = 'in_review', resolved_by = ? WHERE id = ?", (request.state.user["id"], did))
        for uid in (d["opened_by"], d["against_id"]):
            notify(db, uid, "dispute_review", "/dashboard.html#disputes", car=car_title(d))
        return ok(_load(db, did))


@require("admin")
async def admin_resolve_dispute(request: Request):
    did = path_int(request)
    data = await parse_body(request, DisputeResolveIn)
    admin = request.state.user
    with get_db() as db:
        with transaction(db, immediate=True):
            d = _load(db, did)
            if d["status"] not in ACTIVE:
                raise HTTPException(400, tr("Nizo yopilgan"))
            if data.block_user_id and data.block_user_id not in (d["opened_by"], d["against_id"]):
                raise HTTPException(400, tr("Faqat nizo ishtirokchisini bloklash mumkin"))
            status = "rejected" if data.outcome == "rejected" else "resolved"
            db.execute("UPDATE disputes SET status = ?, outcome = ?, decision_note = ?, compensation = ?, resolved_by = ?, "
                       "resolved_at = datetime('now') WHERE id = ?",
                       (status, data.outcome, data.note, data.compensation, admin["id"], did))
            if data.block_user_id:
                db.execute("UPDATE users SET is_active = 0 WHERE id = ? AND role != 'admin'", (data.block_user_id,))
                revoke_user_sessions(db, data.block_user_id)
                audit(db, request, "user_blocked", "user", data.block_user_id, reason=f"dispute #{did}")
            for uid in (d["opened_by"], d["against_id"]):
                notify(db, uid, "dispute_resolved", "/dashboard.html#disputes", car=car_title(d), note=data.note[:140])
            audit(db, request, "dispute_" + status, "dispute", did, outcome=data.outcome, compensation=data.compensation)
        return ok(_load(db, did))


# ---------------- Admin: SMS va email kanallari ----------------
@require("admin")
async def admin_channels(request: Request):
    with get_db() as db:
        log = rows(db.execute("SELECT * FROM message_log ORDER BY id DESC LIMIT 40"))
        stats = dict(db.execute("SELECT status, COUNT(*) FROM message_log WHERE created_at >= datetime('now', '-30 days') GROUP BY status").fetchall())
    templates = [{"key": k, "text": v["uz"], "ru": v["ru"], "en": v["en"]} for k, v in channels.SMS_TEMPLATES.items() if k != "booking"]
    return ok({
        "sms": {"enabled": settings.sms_enabled, "from": settings.ESKIZ_FROM, "account": _mask_email(settings.ESKIZ_EMAIL)},
        "email": {"enabled": settings.email_enabled, "host": ("Gmail (Apps Script)" if settings.EMAIL_RELAY_URL else settings.SMTP_HOST) or None, "from": settings.SMTP_FROM},
        "dev_inbox": settings.DEV_INBOX, "production": settings.ENV == "production", "public_url": settings.PUBLIC_URL,
        "templates": templates, "log": log, "stats_30d": stats,
    })


def _mask_email(e: str) -> str | None:
    if not e or "@" not in e:
        return None
    n, d = e.split("@", 1)
    return n[:2] + "***@" + d


@require("admin")
async def admin_channel_test(request: Request):
    data = await parse_body(request, ChannelTestIn)
    to = data.to.strip()
    if data.channel == "sms":
        to = normalize_phone(to) or ""
        if not to:
            raise HTTPException(400, tr("Telefon raqam noto'g'ri"))
    elif "@" not in to:
        raise HTTPException(400, tr("Email manzil noto'g'ri"))
    try:
        res = channels.send_now(data.channel, to, "test", request.state.user.get("lang") or "uz")
    except channels.DeliveryUnavailable:
        raise HTTPException(400, tr("Kanal sozlanmagan"))
    with get_db() as db:
        audit(db, request, "channel_test", data.channel, None, status=res.get("status"))
    return ok({**res, "to": channels.mask(to)})


async def eskiz_callback(request: Request):
    """Eskiz yetkazib berish holatini yuboradi (DELIVRD, REJECTD...). Imzo — bizning HMAC, shuning uchun soxtalashtirib bo'lmaydi."""
    try:
        log_id = int(request.query_params.get("log", "0"))
    except ValueError:
        return JSONResponse({"ok": False}, status_code=400)
    if not log_id or not hmac.compare_digest(request.query_params.get("sig", ""), channels.callback_sig(log_id)):
        return JSONResponse({"ok": False}, status_code=403)
    try:
        form = dict(await request.form())
    except Exception:
        form = {}
    st = str(form.get("status", "")).upper()
    status = "delivered" if st == "DELIVRD" else "failed" if st in ("REJECTD", "UNDELIV", "EXPIRED", "FAILED") else None
    if status:
        channels._update_log(log_id, status, None if status == "delivered" else st)
    return JSONResponse({"ok": True})


routes = [
    Route("/api/disputes", open_dispute, methods=["POST"]),
    Route("/api/disputes/mine", my_disputes, methods=["GET"]),
    Route("/api/disputes/{id:int}/reply", reply_dispute, methods=["POST"]),
    Route("/api/disputes/{id:int}/withdraw", withdraw_dispute, methods=["POST"]),
    Route("/api/admin/disputes", admin_disputes, methods=["GET"]),
    Route("/api/admin/disputes/{id:int}/take", admin_take_dispute, methods=["POST"]),
    Route("/api/admin/disputes/{id:int}/resolve", admin_resolve_dispute, methods=["POST"]),
    Route("/api/admin/channels", admin_channels, methods=["GET"]),
    Route("/api/admin/channels/test", admin_channel_test, methods=["POST"]),
    Route("/api/channels/eskiz/callback", eskiz_callback, methods=["POST"]),
]
