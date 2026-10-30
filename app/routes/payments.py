"""To'lovlar: test provayder (faqat dev/demo), Click va Payme (kalitlar berilganda), qaytarish va owner'larga to'lovlar.

Oqim: owner bronni tasdiqlaydi -> ijarachi "Onlayn to'lash"ni tanlaydi -> provayder sahifasi -> provayder bizga xabar beradi
-> bron "to'langan" bo'ladi. Depozit har doim joyida (qaytariladigan summa, onlayn olinmaydi).
Har bir pul summasi butun so'mda; Payme tiyinda ishlaydi (so'm × 100).
"""
import base64
import sqlite3
import hashlib
import hmac
import time
import urllib.parse

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from ..config import settings
from ..db import get_db, one, rows, transaction
from ..i18n import tr
from ..schemas import PaymentIn, PayoutIn
from ..security import require
from ..utils import audit, car_title, notify, ok, parse_body, path_int, today

PAYME_TIMEOUT_MS = 12 * 3600 * 1000


def providers() -> dict:
    return {"test": settings.PAYMENT_TEST_MODE, "click": settings.click_enabled, "payme": settings.payme_enabled}


async def list_providers(request: Request):
    return ok(providers())


def _booking_for_payment(db, booking_id: int) -> dict:
    b = one(db.execute("SELECT b.*, c.owner_id, c.brand, c.model, c.year FROM bookings b JOIN cars c ON c.id = b.car_id WHERE b.id = ?",
                       (booking_id,)))
    if not b:
        raise HTTPException(404, tr("Bron topilmadi"))
    return b


def checkout_url(provider: str, payment_id: int, amount: int) -> str:
    back = f"{settings.PUBLIC_URL}/receipt.html?payment={payment_id}"
    if provider == "test":
        return f"/pay.html?payment={payment_id}"
    if provider == "click":
        q = urllib.parse.urlencode({"service_id": settings.CLICK_SERVICE_ID, "merchant_id": settings.CLICK_MERCHANT_ID,
                                    "amount": amount, "transaction_param": payment_id, "return_url": back})
        return "https://my.click.uz/services/pay?" + q
    raw = f"m={settings.PAYME_MERCHANT_ID};ac.order_id={payment_id};a={amount * 100};c={back}"
    return "https://checkout.paycom.uz/" + base64.b64encode(raw.encode()).decode()


@require("user")
async def create_payment(request: Request):
    data = await parse_body(request, PaymentIn)
    user = request.state.user
    if not providers().get(data.provider):
        raise HTTPException(400, tr("Bu to'lov usuli hozircha ulanmagan"))
    with get_db() as db:
        with transaction(db, immediate=True):
            b = _booking_for_payment(db, data.booking_id)
            if b["renter_id"] != user["id"]:
                raise HTTPException(403, tr("Bu bron sizga tegishli emas"))
            if b["status"] != "approved":
                raise HTTPException(400, tr("To'lov faqat owner tasdiqlagan bron uchun mumkin"))
            if b["payment_status"] == "paid":
                raise HTTPException(409, tr("Bu bron allaqachon to'langan"))
            if b["end_date"] < today().isoformat():
                raise HTTPException(400, tr("Bu bron uchun to'lov muddati o'tgan"))
            # Bir xil provayderdagi tugallanmagan to'lov qayta ishlatiladi (ikki marta yechilishining oldi olinadi)
            p = one(db.execute("SELECT * FROM payments WHERE booking_id = ? AND provider = ? AND status IN ('created', 'pending') "
                               "ORDER BY id DESC LIMIT 1", (b["id"], data.provider)))
            if not p:
                cur = db.execute("INSERT INTO payments (booking_id, user_id, provider, amount) VALUES (?, ?, ?, ?)",
                                 (b["id"], user["id"], data.provider, b["total_price"]))
                p = one(db.execute("SELECT * FROM payments WHERE id = ?", (cur.lastrowid,)))
    return ok({"payment_id": p["id"], "amount": p["amount"], "redirect_url": checkout_url(p["provider"], p["id"], p["amount"])}, 201)


def _payment_view(db, pid: int, user: dict) -> dict:
    p = one(db.execute(
        """SELECT p.*, b.start_date, b.end_date, b.days, b.price_per_day, b.delivery, b.deposit, b.commission, b.owner_payout,
                  b.status AS booking_status, b.car_id, c.brand, c.model, c.year, c.city, c.owner_id,
                  ru.full_name AS renter_name, ou.full_name AS owner_name
           FROM payments p JOIN bookings b ON b.id = p.booking_id JOIN cars c ON c.id = b.car_id
           JOIN users ru ON ru.id = b.renter_id JOIN users ou ON ou.id = c.owner_id WHERE p.id = ?""", (pid,)))
    # IDOR himoyasi: faqat to'lovchi, avtomobil egasi yoki admin ko'radi
    if not p or user["id"] not in (p["user_id"], p["owner_id"]) and user["role"] != "admin":
        raise HTTPException(404, tr("To'lov topilmadi"))
    if user["id"] != p["user_id"] and user["role"] != "admin":
        p.pop("commission", None)
    return p


@require()
async def get_payment(request: Request):
    with get_db() as db:
        p = _payment_view(db, path_int(request), request.state.user)
    p["test_mode"] = p["provider"] == "test"
    return ok(p)


def mark_paid(db, payment: dict, txn_id: str | None = None) -> None:
    """To'lov muvaffaqiyatli: bron to'langan deb belgilanadi, ikki tomonga bildirishnoma. Takroriy chaqiruv xavfsiz."""
    if payment["status"] == "paid":
        return
    db.execute("UPDATE payments SET status = 'paid', paid_at = datetime('now'), provider_txn_id = COALESCE(?, provider_txn_id) "
               "WHERE id = ?", (txn_id, payment["id"]))
    db.execute("UPDATE bookings SET payment_status = 'paid', updated_at = datetime('now') WHERE id = ?", (payment["booking_id"],))
    # Shu bron uchun boshqa tugallanmagan urinishlar bekor qilinadi
    db.execute("UPDATE payments SET status = 'cancelled', cancelled_at = datetime('now') WHERE booking_id = ? AND id != ? "
               "AND status IN ('created', 'pending')", (payment["booking_id"], payment["id"]))
    b = _booking_for_payment(db, payment["booking_id"])
    notify(db, b["renter_id"], "payment_paid", f"/receipt.html?payment={payment['id']}", car=car_title(b), total=payment["amount"])
    notify(db, b["owner_id"], "payment_paid_owner", "/dashboard.html?mode=owner#earnings", car=car_title(b), total=b["owner_payout"])


def refund_for_booking(db, booking: dict) -> str | None:
    """Bron bekor qilinganda chaqiriladi. Test to'lov darhol qaytariladi; real provayderda admin tasdiqlashi kerak."""
    p = one(db.execute("SELECT * FROM payments WHERE booking_id = ? AND status = 'paid'", (booking["id"],)))
    if not p:
        return None
    status = "refunded" if p["provider"] == "test" else "refund_pending"
    db.execute("UPDATE payments SET status = ?, cancelled_at = datetime('now') WHERE id = ?", (status, p["id"]))
    db.execute("UPDATE bookings SET payment_status = ? WHERE id = ?", (status, booking["id"]))
    notify(db, p["user_id"], "payment_refunded" if status == "refunded" else "payment_refund_pending",
           f"/receipt.html?payment={p['id']}", total=p["amount"])
    return status


# ---------------- Test provayder (faqat dev/demo) ----------------
@require("user")
async def test_confirm(request: Request):
    if not settings.PAYMENT_TEST_MODE:
        raise HTTPException(404, tr("API manzili topilmadi"))
    pid = path_int(request)
    with get_db() as db:
        with transaction(db, immediate=True):
            p = one(db.execute("SELECT * FROM payments WHERE id = ?", (pid,)))
            if not p or p["user_id"] != request.state.user["id"] or p["provider"] != "test":
                raise HTTPException(404, tr("To'lov topilmadi"))
            if p["status"] not in ("created", "pending", "paid"):
                raise HTTPException(400, tr("Bu to'lovni yakunlab bo'lmaydi"))
            b = _booking_for_payment(db, p["booking_id"])
            if b["status"] != "approved":
                raise HTTPException(400, tr("To'lov faqat owner tasdiqlagan bron uchun mumkin"))
            mark_paid(db, p, f"test-{pid}-{int(time.time())}")
    return ok({"payment_id": pid, "status": "paid"})


@require("user")
async def test_cancel(request: Request):
    pid = path_int(request)
    with get_db() as db:
        db.execute("UPDATE payments SET status = 'cancelled', cancelled_at = datetime('now') WHERE id = ? AND user_id = ? "
                   "AND status IN ('created', 'pending')", (pid, request.state.user["id"]))
    return ok()


# ---------------- Click (SHOP API: prepare / complete) ----------------
def click_sign(f: dict, prepare_id: str = "") -> str:
    base = (f.get("click_trans_id", "") + f.get("service_id", "") + settings.CLICK_SECRET_KEY + f.get("merchant_trans_id", "")
            + prepare_id + f.get("amount", "") + f.get("action", "") + f.get("sign_time", ""))
    return hashlib.md5(base.encode()).hexdigest()


def _click_reply(f: dict, error: int, note: str, **extra):
    return JSONResponse({"click_trans_id": f.get("click_trans_id"), "merchant_trans_id": f.get("merchant_trans_id"),
                         "error": error, "error_note": note, **extra})


async def click_callback(request: Request):
    if not settings.click_enabled:
        raise HTTPException(404, tr("API manzili topilmadi"))
    f = {k: str(v) for k, v in (await request.form()).items()}
    action = f.get("action")
    complete = action == "1"
    if not hmac.compare_digest(f.get("sign_string", ""), click_sign(f, f.get("merchant_prepare_id", "") if complete else "")):
        return _click_reply(f, -1, "SIGN CHECK FAILED")
    if action not in ("0", "1"):
        return _click_reply(f, -3, "Action not found")
    try:
        pid = int(f.get("merchant_trans_id", "0"))
    except ValueError:
        return _click_reply(f, -5, "Order not found")
    with get_db() as db:
        with transaction(db, immediate=True):
            p = one(db.execute("SELECT * FROM payments WHERE id = ? AND provider = 'click'", (pid,)))
            if not p:
                return _click_reply(f, -5, "Order not found")
            try:
                amount_ok = abs(float(f.get("amount", "0")) - p["amount"]) < 0.01
            except ValueError:
                amount_ok = False
            if not amount_ok:
                return _click_reply(f, -2, "Incorrect parameter amount")
            if p["status"] == "paid":
                return _click_reply(f, -4, "Already paid")
            if p["status"] in ("cancelled", "refunded", "refund_pending", "failed"):
                return _click_reply(f, -9, "Transaction cancelled")
            b = _booking_for_payment(db, p["booking_id"])
            if b["status"] != "approved":
                return _click_reply(f, -9, "Transaction cancelled")
            if not complete:
                try:
                    db.execute("UPDATE payments SET status = 'pending', provider_txn_id = ? WHERE id = ?", (f.get("click_trans_id"), pid))
                except sqlite3.IntegrityError:
                    return _click_reply(f, -8, "Error in request from click")
                return _click_reply(f, 0, "Success", merchant_prepare_id=pid)
            if f.get("merchant_prepare_id") != str(pid) or p["status"] != "pending":
                return _click_reply(f, -6, "Transaction does not exist")
            if int(f.get("error", "0") or 0) < 0:   # Click to'lovni bekor qildi
                db.execute("UPDATE payments SET status = 'cancelled', cancelled_at = datetime('now') WHERE id = ?", (pid,))
                return _click_reply(f, -9, "Transaction cancelled")
            mark_paid(db, p, f.get("click_trans_id"))
            return _click_reply(f, 0, "Success", merchant_confirm_id=pid)


# ---------------- Payme (Merchant API, JSON-RPC 2.0) ----------------
class PaymeError(Exception):
    def __init__(self, code: int, msg: str, data: str | None = None):
        self.code, self.msg, self.data = code, msg, data


def _payme_ms() -> int:
    return int(time.time() * 1000)


def _payme_auth_ok(request: Request) -> bool:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Basic "):
        return False
    try:
        login, _, key = base64.b64decode(auth[6:]).decode().partition(":")
    except Exception:
        return False
    return login == "Paycom" and hmac.compare_digest(key, settings.PAYME_KEY)


def _payme_order(db, account: dict, amount_tiyin: int) -> dict:
    try:
        pid = int((account or {}).get("order_id", 0))
    except (TypeError, ValueError):
        pid = 0
    p = one(db.execute("SELECT * FROM payments WHERE id = ? AND provider = 'payme'", (pid,)))
    if not p:
        raise PaymeError(-31050, "Order not found", "order_id")
    if p["amount"] * 100 != amount_tiyin:
        raise PaymeError(-31001, "Incorrect amount")
    b = _booking_for_payment(db, p["booking_id"])
    if b["status"] != "approved" or p["status"] not in ("created", "pending"):
        raise PaymeError(-31050, "Order is not available", "order_id")
    return p


def _payme_txn(p: dict) -> dict:
    state = p["provider_state"] or 0
    return {"create_time": p["provider_time"] or 0, "perform_time": p.get("perform_ms") or 0,
            "cancel_time": p.get("cancel_ms") or 0, "transaction": str(p["id"]), "state": state, "reason": p["reason"]}


def payme_dispatch(db, method: str, params: dict) -> dict:
    if method == "CheckPerformTransaction":
        _payme_order(db, params.get("account"), int(params.get("amount", 0)))
        return {"allow": True}
    if method == "CreateTransaction":
        txn_id = str(params.get("id", ""))
        existing = one(db.execute("SELECT * FROM payments WHERE provider = 'payme' AND provider_txn_id = ?", (txn_id,)))
        if existing:
            if existing["provider_state"] != 1:
                raise PaymeError(-31008, "Transaction is not active")
            if _payme_ms() - (existing["provider_time"] or 0) > PAYME_TIMEOUT_MS:
                db.execute("UPDATE payments SET provider_state = -1, reason = 4, status = 'cancelled', cancelled_at = datetime('now') "
                           "WHERE id = ?", (existing["id"],))
                raise PaymeError(-31008, "Transaction timed out")
            return {"create_time": existing["provider_time"], "transaction": str(existing["id"]), "state": 1}
        p = _payme_order(db, params.get("account"), int(params.get("amount", 0)))
        if p["provider_txn_id"] and p["provider_txn_id"] != txn_id:
            raise PaymeError(-31050, "Order has another transaction", "order_id")
        t = int(params.get("time", _payme_ms()))
        db.execute("UPDATE payments SET provider_txn_id = ?, provider_state = 1, provider_time = ?, status = 'pending' WHERE id = ?",
                   (txn_id, t, p["id"]))
        return {"create_time": t, "transaction": str(p["id"]), "state": 1}
    if method in ("PerformTransaction", "CancelTransaction", "CheckTransaction"):
        p = one(db.execute("SELECT * FROM payments WHERE provider = 'payme' AND provider_txn_id = ?", (str(params.get("id", "")),)))
        if not p:
            raise PaymeError(-31003, "Transaction not found")
        meta = one(db.execute("SELECT paid_at, cancelled_at FROM payments WHERE id = ?", (p["id"],)))
        p["perform_ms"] = _to_ms(meta["paid_at"])
        p["cancel_ms"] = _to_ms(meta["cancelled_at"])
        if method == "CheckTransaction":
            return _payme_txn(p)
        if method == "PerformTransaction":
            if p["provider_state"] == 2:
                return {"transaction": str(p["id"]), "perform_time": p["perform_ms"], "state": 2}
            if p["provider_state"] != 1:
                raise PaymeError(-31008, "Transaction is not active")
            if _payme_ms() - (p["provider_time"] or 0) > PAYME_TIMEOUT_MS:
                db.execute("UPDATE payments SET provider_state = -1, reason = 4, status = 'cancelled', cancelled_at = datetime('now') "
                           "WHERE id = ?", (p["id"],))
                raise PaymeError(-31008, "Transaction timed out")
            db.execute("UPDATE payments SET provider_state = 2 WHERE id = ?", (p["id"],))
            mark_paid(db, p)
            paid_at = db.execute("SELECT paid_at FROM payments WHERE id = ?", (p["id"],)).fetchone()[0]
            return {"transaction": str(p["id"]), "perform_time": _to_ms(paid_at), "state": 2}
        # CancelTransaction
        reason = int(params.get("reason", 0) or 0)
        if p["provider_state"] in (-1, -2):
            return {"transaction": str(p["id"]), "cancel_time": p["cancel_ms"], "state": p["provider_state"]}
        new_state = -1 if p["provider_state"] == 1 else -2
        db.execute("UPDATE payments SET provider_state = ?, reason = ?, status = ?, cancelled_at = datetime('now') WHERE id = ?",
                   (new_state, reason, "cancelled" if new_state == -1 else "refunded", p["id"]))
        if new_state == -2:
            db.execute("UPDATE bookings SET payment_status = 'refunded' WHERE id = ?", (p["booking_id"],))
        return {"transaction": str(p["id"]), "cancel_time": _payme_ms(), "state": new_state}
    if method == "GetStatement":
        items = rows(db.execute("SELECT * FROM payments WHERE provider = 'payme' AND provider_time BETWEEN ? AND ? ORDER BY provider_time",
                                (int(params.get("from", 0)), int(params.get("to", 0)))))
        out = []
        for p in items:
            meta = one(db.execute("SELECT paid_at, cancelled_at FROM payments WHERE id = ?", (p["id"],)))
            p["perform_ms"], p["cancel_ms"] = _to_ms(meta["paid_at"]), _to_ms(meta["cancelled_at"])
            out.append({"id": p["provider_txn_id"], "time": p["provider_time"], "amount": p["amount"] * 100,
                        "account": {"order_id": str(p["id"])}, **_payme_txn(p)})
        return {"transactions": out}
    raise PaymeError(-32601, "Method not found")


def _to_ms(ts: str | None) -> int:
    if not ts:
        return 0
    from datetime import datetime, timezone
    return int(datetime.fromisoformat(ts).replace(tzinfo=timezone.utc).timestamp() * 1000)


async def payme_rpc(request: Request):
    if not settings.payme_enabled:
        raise HTTPException(404, tr("API manzili topilmadi"))
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
    rid = body.get("id") if isinstance(body, dict) else None
    if not _payme_auth_ok(request):
        return JSONResponse({"jsonrpc": "2.0", "id": rid, "error": {"code": -32504, "message": "Insufficient privileges"}})
    try:
        with get_db() as db, transaction(db, immediate=True):
            result = payme_dispatch(db, str(body.get("method", "")), body.get("params") or {})
        return JSONResponse({"jsonrpc": "2.0", "id": rid, "result": result})
    except PaymeError as e:
        err = {"code": e.code, "message": {"uz": e.msg, "ru": e.msg, "en": e.msg}}
        if e.data:
            err["data"] = e.data
        return JSONResponse({"jsonrpc": "2.0", "id": rid, "error": err})


# ---------------- Owner daromadi va admin moliya ----------------
def owner_balance(db, owner_id: int) -> dict:
    earned = db.execute(
        "SELECT COALESCE(SUM(b.owner_payout), 0) FROM bookings b JOIN cars c ON c.id = b.car_id "
        "WHERE c.owner_id = ? AND b.payment_status = 'paid' AND b.status IN ('approved', 'completed')", (owner_id,)).fetchone()[0]
    on_site = db.execute(
        "SELECT COALESCE(SUM(b.owner_payout), 0) FROM bookings b JOIN cars c ON c.id = b.car_id "
        "WHERE c.owner_id = ? AND b.payment_status = 'on_site' AND b.status IN ('approved', 'completed')", (owner_id,)).fetchone()[0]
    paid_out = db.execute("SELECT COALESCE(SUM(amount), 0) FROM payouts WHERE owner_id = ?", (owner_id,)).fetchone()[0]
    return {"earned_online": earned, "on_site": on_site, "paid_out": paid_out, "balance": earned - paid_out}


@require()
async def my_earnings(request: Request):
    uid = request.state.user["id"]
    with get_db() as db:
        bal = owner_balance(db, uid)
        bal["payouts"] = rows(db.execute("SELECT amount, note, created_at FROM payouts WHERE owner_id = ? ORDER BY id DESC LIMIT 50", (uid,)))
        bal["payments"] = rows(db.execute(
            """SELECT p.id, p.provider, p.status, p.paid_at, b.owner_payout, b.start_date, b.end_date, c.brand, c.model, c.year
               FROM payments p JOIN bookings b ON b.id = p.booking_id JOIN cars c ON c.id = b.car_id
               WHERE c.owner_id = ? AND p.status IN ('paid', 'refunded', 'refund_pending') ORDER BY p.id DESC LIMIT 100""", (uid,)))
    return ok(bal)


@require("admin")
async def admin_payments(request: Request):
    with get_db() as db:
        items = rows(db.execute(
            """SELECT p.*, c.brand, c.model, ru.full_name AS renter_name FROM payments p JOIN bookings b ON b.id = p.booking_id
               JOIN cars c ON c.id = b.car_id JOIN users ru ON ru.id = p.user_id ORDER BY p.id DESC LIMIT 300"""))
        owners = rows(db.execute("SELECT DISTINCT u.id, u.full_name FROM users u JOIN cars c ON c.owner_id = u.id ORDER BY u.full_name"))
        balances = [{**o, **owner_balance(db, o["id"])} for o in owners]
    return ok({"items": items, "balances": [b for b in balances if b["earned_online"] or b["paid_out"]], "providers": providers()})


@require("admin")
async def admin_mark_refunded(request: Request):
    pid = path_int(request)
    with get_db() as db:
        p = one(db.execute("SELECT * FROM payments WHERE id = ?", (pid,)))
        if not p or p["status"] != "refund_pending":
            raise HTTPException(400, tr("Bu to'lov qaytarish kutilayotgan holatda emas"))
        db.execute("UPDATE payments SET status = 'refunded' WHERE id = ?", (pid,))
        db.execute("UPDATE bookings SET payment_status = 'refunded' WHERE id = ?", (p["booking_id"],))
        notify(db, p["user_id"], "payment_refunded", f"/receipt.html?payment={pid}", total=p["amount"])
        audit(db, request, "payment_refunded", "payment", pid, amount=p["amount"])
    return ok()


@require("admin")
async def admin_payout(request: Request):
    data = await parse_body(request, PayoutIn)
    with get_db() as db:
        bal = owner_balance(db, data.owner_id)
        if data.amount > bal["balance"]:
            raise HTTPException(400, tr("Summa owner balansidan katta"))
        db.execute("INSERT INTO payouts (owner_id, amount, note, created_by) VALUES (?, ?, ?, ?)",
                   (data.owner_id, data.amount, data.note, request.state.user["id"]))
        notify(db, data.owner_id, "payout_sent", "/dashboard.html?mode=owner#earnings", total=data.amount)
        audit(db, request, "payout_sent", "user", data.owner_id, amount=data.amount)
        return ok(owner_balance(db, data.owner_id))


routes = [
    Route("/api/payments/providers", list_providers, methods=["GET"]),
    Route("/api/payments", create_payment, methods=["POST"]),
    Route("/api/payments/{id:int}", get_payment, methods=["GET"]),
    Route("/api/payments/{id:int}/test/confirm", test_confirm, methods=["POST"]),
    Route("/api/payments/{id:int}/test/cancel", test_cancel, methods=["POST"]),
    Route("/api/payments/click", click_callback, methods=["POST"]),
    Route("/api/payments/payme", payme_rpc, methods=["POST"]),
    Route("/api/my/earnings", my_earnings, methods=["GET"]),
    Route("/api/admin/payments", admin_payments, methods=["GET"]),
    Route("/api/admin/payments/{id:int}/refunded", admin_mark_refunded, methods=["POST"]),
    Route("/api/admin/payouts", admin_payout, methods=["POST"]),
]
