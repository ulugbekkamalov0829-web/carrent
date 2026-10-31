"""To'lovlar: test provayder (faqat dev/demo), Click va Payme (kalitlar berilganda), qaytarish va owner'larga to'lovlar.

Oqim: owner bronni tasdiqlaydi -> ijarachi "Onlayn to'lash"ni tanlaydi -> provayder sahifasi -> provayder bizga xabar beradi
-> bron "to'langan" bo'ladi. Depozit har doim joyida (qaytariladigan summa, onlayn olinmaydi).
Har bir pul summasi butun so'mda; Payme tiyinda ishlaydi (so'm × 100).

Bekor qilish siyosati (REFUND_RULES): ijara boshlanishiga 3+ kun qolganda 100%, 1–2 kun qolganda 50% qaytariladi.
Qaytarilmagan qism ham komissiya foizi bo'yicha bo'linadi: owner o'z ulushini oladi (bo'sh qolgan kunlar uchun kompensatsiya).
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
from ..schemas import FeeSettlementIn, PaymentIn, PayoutDecisionIn, PayoutIn, PayoutRequestIn
from ..security import require
from ..utils import audit, bps_split, car_title, notify, ok, parse_body, path_int, today

PAYME_TIMEOUT_MS = 12 * 3600 * 1000
CHECKOUT_TTL_MIN = 30          # yaratilgan, lekin to'lov sahifasiga o'tilmagan urinish shuncha daqiqadan keyin yopiladi
CLICK_PENDING_TTL_MIN = 60     # Click "prepare"dan keyin "complete" kelmasa
# (ijara boshlanishiga kamida necha kun qolgan, qaytariladigan foiz) — kattadan kichikka
REFUND_RULES = ((3, 100), (1, 50))


def refund_percent(start_date: str, on=None) -> tuple[int, int]:
    """(qaytariladigan foiz, boshlanishgacha qolgan kunlar)."""
    from datetime import date
    days_before = (date.fromisoformat(start_date) - (on or today())).days
    for min_days, pct in REFUND_RULES:
        if days_before >= min_days:
            return pct, days_before
    return 0, days_before


def cancel_preview(db, booking: dict) -> dict:
    """Bekor qilinsa nima bo'lishi: ijarachi tasdiqlashdan oldin aniq summani ko'radi."""
    p = one(db.execute("SELECT * FROM payments WHERE booking_id = ? AND status = 'paid'", (booking["id"],)))
    pct, days_before = refund_percent(booking["start_date"])
    if not p:
        return {"paid": False, "amount": 0, "refund": 0, "kept": 0, "pct": 100, "days_before": days_before}
    refund = p["amount"] * pct // 100
    return {"paid": True, "amount": p["amount"], "refund": refund, "kept": p["amount"] - refund, "pct": pct,
            "days_before": days_before, "provider": p["provider"]}


def maintain_payments(db) -> None:
    """Arzon fon vazifasi: eskirgan urinishlarni yopadi (bron sahifasini ochganda ham, to'lovda ham chaqiriladi)."""
    db.execute(f"""UPDATE payments SET status = 'cancelled', cancelled_at = datetime('now')
                   WHERE status = 'created' AND created_at < datetime('now', '-{CHECKOUT_TTL_MIN} minutes')""")
    db.execute(f"""UPDATE payments SET status = 'cancelled', cancelled_at = datetime('now')
                   WHERE status = 'pending' AND provider = 'click' AND created_at < datetime('now', '-{CLICK_PENDING_TTL_MIN} minutes')""")
    # Bron endi tasdiqlangan holatda emas (bekor, rad, yakunlangan) — ochiq urinishlar ham yopiladi (Payme o'z vaqtida yopadi)
    db.execute("""UPDATE payments SET status = 'cancelled', cancelled_at = datetime('now')
                  WHERE status IN ('created', 'pending') AND provider != 'payme'
                  AND booking_id IN (SELECT id FROM bookings WHERE status != 'approved')""")


def providers() -> dict:
    return {"test": settings.PAYMENT_TEST_MODE, "click": settings.click_enabled, "payme": settings.payme_enabled}


async def list_providers(request: Request):
    return ok({**providers(), "policy": [{"min_days": d, "pct": p} for d, p in REFUND_RULES]})


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
        # Click hujjati: summa N.NN ko'rinishida (docs.click.uz/en/?p=101)
        q = urllib.parse.urlencode({"service_id": settings.CLICK_SERVICE_ID, "merchant_id": settings.CLICK_MERCHANT_ID,
                                    "amount": f"{amount:.2f}", "transaction_param": payment_id, "return_url": back})
        return "https://my.click.uz/services/pay?" + q
    raw = f"m={settings.PAYME_MERCHANT_ID};ac.order_id={payment_id};a={amount * 100};c={back}"
    base = "https://test.paycom.uz/" if settings.PAYME_TEST else "https://checkout.paycom.uz/"
    return base + base64.b64encode(raw.encode()).decode()


@require("user")
async def create_payment(request: Request):
    data = await parse_body(request, PaymentIn)
    user = request.state.user
    if not providers().get(data.provider):
        raise HTTPException(400, tr("Bu to'lov usuli hozircha ulanmagan"))
    with get_db() as db:
        maintain_payments(db)
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


def refund_for_booking(db, booking: dict) -> dict | None:
    """Bron bekor qilinganda chaqiriladi. Qaytariladigan summa REFUND_RULES bo'yicha.
    Test to'lov darhol qaytariladi; Click/Payme'da admin pulni qaytarib, tizimda belgilaydi."""
    pv = cancel_preview(db, booking)
    if not pv["paid"]:
        return None
    p = one(db.execute("SELECT * FROM payments WHERE booking_id = ? AND status = 'paid'", (booking["id"],)))
    kept_commission, kept_payout = bps_split(pv["kept"], booking["commission_bps"])
    if pv["refund"] == 0:
        status = "paid"          # pul qaytarilmaydi: to'lov kuchda qoladi, owner kompensatsiya oladi
    else:
        status = "refunded" if p["provider"] == "test" else "refund_pending"
    db.execute("UPDATE payments SET status = ?, refund_amount = ?, kept_commission = ?, kept_payout = ?, "
               "cancelled_at = CASE WHEN ? != 'paid' THEN datetime('now') ELSE cancelled_at END WHERE id = ?",
               (status, pv["refund"], kept_commission, kept_payout, status, p["id"]))
    db.execute("UPDATE bookings SET payment_status = ? WHERE id = ?", (status, booking["id"]))
    if pv["refund"]:
        notify(db, p["user_id"], "payment_refunded" if status == "refunded" else "payment_refund_pending",
               f"/receipt.html?payment={p['id']}", total=pv["refund"])
    if kept_payout:
        notify(db, booking["owner_id"], "cancel_compensation", "/dashboard.html?mode=owner#earnings",
               car=car_title(booking), total=kept_payout)
    return {**pv, "status": status}


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


def _payme_key(db) -> str:
    """Payme kassasi kalitni ChangePassword orqali almashtirishi mumkin: yangisi bazada saqlanadi va .env'dagidan ustun."""
    from ..db import get_setting
    return get_setting(db, "payme_key", "") or settings.PAYME_KEY


def _payme_auth_ok(request: Request, key_expected: str) -> bool:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Basic ") or not key_expected:
        return False
    try:
        login, _, key = base64.b64decode(auth[6:]).decode().partition(":")
    except Exception:
        return False
    return login == "Paycom" and hmac.compare_digest(key.encode(), key_expected.encode())


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
        p = _payme_order(db, params.get("account"), int(params.get("amount", 0)))
        if p["status"] == "pending" and p["provider_txn_id"]:
            raise PaymeError(-31050, "Order has an active transaction", "order_id")   # bir buyurtma — bitta faol tranzaksiya
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
            b = _booking_for_payment(db, p["booking_id"])
            if b["status"] != "approved" or b["payment_status"] == "paid":
                # Ijarachi kutish paytida bronni bekor qildi yoki boshqa usulda to'ladi: pul yechilmaydi
                db.execute("UPDATE payments SET provider_state = -1, reason = 3, status = 'cancelled', cancelled_at = datetime('now') "
                           "WHERE id = ?", (p["id"],))
                raise PaymeError(-31008, "Order is no longer available")
            db.execute("UPDATE payments SET provider_state = 2 WHERE id = ?", (p["id"],))
            mark_paid(db, p)
            paid_at = db.execute("SELECT paid_at FROM payments WHERE id = ?", (p["id"],)).fetchone()[0]
            return {"transaction": str(p["id"]), "perform_time": _to_ms(paid_at), "state": 2}
        # CancelTransaction
        reason = int(params.get("reason", 0) or 0)
        if p["provider_state"] in (-1, -2):
            return {"transaction": str(p["id"]), "cancel_time": p["cancel_ms"], "state": p["provider_state"]}
        new_state = -1 if p["provider_state"] == 1 else -2
        if new_state == -2:
            b = _booking_for_payment(db, p["booking_id"])
            if b["status"] == "completed":
                raise PaymeError(-31007, "Unable to cancel: service already provided")   # ijara o'tib bo'lgan
        db.execute("UPDATE payments SET provider_state = ?, reason = ?, status = ?, cancelled_at = datetime('now'), "
                   "refund_amount = CASE WHEN ? = -2 THEN amount ELSE refund_amount END, kept_commission = 0, kept_payout = 0 WHERE id = ?",
                   (new_state, reason, "cancelled" if new_state == -1 else "refunded", new_state, p["id"]))
        if new_state == -2:
            db.execute("UPDATE bookings SET payment_status = 'refunded' WHERE id = ?", (p["booking_id"],))
            notify(db, p["user_id"], "payment_refunded", f"/receipt.html?payment={p['id']}", total=p["amount"])
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
    if method == "ChangePassword":
        new = str(params.get("password", ""))
        if len(new) < 8:
            raise PaymeError(-32600, "Invalid password")
        db.execute("INSERT INTO settings (key, value) VALUES ('payme_key', ?) "
                   "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')", (new,))
        return {"success": True}
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
    with get_db() as db:
        key = _payme_key(db)
    if not _payme_auth_ok(request, key):
        return JSONResponse({"jsonrpc": "2.0", "id": rid, "error": {"code": -32504, "message": "Insufficient privileges"}})
    # PaymeError tranzaksiyani bekor qilmaydi: xatodan oldingi holat o'zgarishi (masalan, vaqti o'tgan
    # tranzaksiyani "bekor" deb belgilash) saqlanib qolishi kerak — aks holda Payme keyingi so'rovda eski holatni ko'radi.
    with get_db() as db, transaction(db, immediate=True):
        try:
            result, error = payme_dispatch(db, str(body.get("method", "")), body.get("params") or {}), None
        except PaymeError as e:
            result, error = None, e
    if error is None:
        return JSONResponse({"jsonrpc": "2.0", "id": rid, "result": result})
    err = {"code": error.code, "message": {"uz": error.msg, "ru": error.msg, "en": error.msg}}
    if error.data:
        err["data"] = error.data
    return JSONResponse({"jsonrpc": "2.0", "id": rid, "error": err})


# ---------------- Owner daromadi va admin moliya ----------------
def owner_balance(db, owner_id: int) -> dict:
    earned = db.execute(
        "SELECT COALESCE(SUM(b.owner_payout), 0) FROM bookings b JOIN cars c ON c.id = b.car_id "
        "WHERE c.owner_id = ? AND b.payment_status = 'paid' AND b.status IN ('approved', 'completed')", (owner_id,)).fetchone()[0]
    compensation = db.execute(
        "SELECT COALESCE(SUM(p.kept_payout), 0) FROM payments p JOIN bookings b ON b.id = p.booking_id JOIN cars c ON c.id = b.car_id "
        "WHERE c.owner_id = ? AND b.status = 'cancelled' AND p.status IN ('paid', 'refunded', 'refund_pending')", (owner_id,)).fetchone()[0]
    earned += compensation
    requested = db.execute("SELECT COALESCE(SUM(amount), 0) FROM payout_requests WHERE owner_id = ? AND status = 'pending'",
                           (owner_id,)).fetchone()[0]
    on_site = db.execute(
        "SELECT COALESCE(SUM(b.owner_payout), 0) FROM bookings b JOIN cars c ON c.id = b.car_id "
        "WHERE c.owner_id = ? AND b.payment_status = 'on_site' AND b.status IN ('approved', 'completed')", (owner_id,)).fetchone()[0]
    # Yakunlangan joyida-to'lov ijaralar: pul ownerda, komissiya platformaga qarz
    site = db.execute(
        "SELECT COALESCE(SUM(b.total_price), 0), COALESCE(SUM(b.commission), 0) FROM bookings b JOIN cars c ON c.id = b.car_id "
        "WHERE c.owner_id = ? AND b.payment_status = 'on_site' AND b.status = 'completed'", (owner_id,)).fetchone()
    settled = db.execute("SELECT COALESCE(SUM(amount), 0) FROM fee_settlements WHERE owner_id = ?", (owner_id,)).fetchone()[0]
    fee_owed = max(0, site[1] - settled)
    paid_out = db.execute("SELECT COALESCE(SUM(amount), 0) FROM payouts WHERE owner_id = ?", (owner_id,)).fetchone()[0]
    balance = earned - paid_out
    return {"earned_online": earned, "compensation": compensation, "on_site": on_site, "paid_out": paid_out,
            "site_collected": site[0], "fee_total": site[1], "fee_settled": settled, "fee_owed": fee_owed,
            "balance": balance, "requested": requested,
            # Yechib olinadigan summa: balans − ko'rib chiqilayotgan so'rovlar − komissiya qarzi (qarz balansdan ushlanishi mumkin)
            "available": max(0, balance - requested - fee_owed)}


@require()
async def my_earnings(request: Request):
    uid = request.state.user["id"]
    with get_db() as db:
        bal = owner_balance(db, uid)
        bal["payouts"] = rows(db.execute("SELECT amount, note, created_at FROM payouts WHERE owner_id = ? ORDER BY id DESC LIMIT 50", (uid,)))
        bal["requests"] = rows(db.execute("SELECT * FROM payout_requests WHERE owner_id = ? ORDER BY id DESC LIMIT 30", (uid,)))
        bal["payments"] = rows(db.execute(
            """SELECT p.id, p.provider, p.status, p.paid_at, p.refund_amount, p.kept_payout, b.status AS booking_status,
                      b.owner_payout, b.start_date, b.end_date, c.brand, c.model, c.year
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
    return ok({"items": items, "balances": [b for b in balances if b["earned_online"] or b["paid_out"] or b["fee_owed"]],
               "providers": providers()})


@require("admin")
async def admin_fee_settlement(request: Request):
    """Komissiya qarzini yopish: naqd to'landi deb belgilash yoki owner onlayn balansidan ushlash."""
    data = await parse_body(request, FeeSettlementIn)
    admin = request.state.user
    with get_db() as db:
        with transaction(db, immediate=True):
            bal = owner_balance(db, data.owner_id)
            if data.amount > bal["fee_owed"]:
                raise HTTPException(400, tr("Summa komissiya qarzidan katta"))
            if data.from_balance and data.amount > bal["balance"] - bal["requested"]:
                raise HTTPException(400, tr("Summa owner balansidan katta"))
            note = data.note or tr("Komissiya qarzi hisobidan")
            if data.from_balance:   # balansdagi pul platformada qoladi: bu owner uchun "o'tkazma" sifatida yoziladi
                db.execute("INSERT INTO payouts (owner_id, amount, note, created_by) VALUES (?, ?, ?, ?)",
                           (data.owner_id, data.amount, note, admin["id"]))
            db.execute("INSERT INTO fee_settlements (owner_id, amount, from_balance, note, created_by) VALUES (?, ?, ?, ?, ?)",
                       (data.owner_id, data.amount, int(data.from_balance), note, admin["id"]))
            notify(db, data.owner_id, "fee_settled", "/dashboard.html?mode=owner#earnings", total=data.amount)
            audit(db, request, "fee_settled", "user", data.owner_id, amount=data.amount, from_balance=data.from_balance)
        return ok(owner_balance(db, data.owner_id))


@require("admin")
async def admin_mark_refunded(request: Request):
    pid = path_int(request)
    with get_db() as db:
        p = one(db.execute("SELECT * FROM payments WHERE id = ?", (pid,)))
        if not p or p["status"] != "refund_pending":
            raise HTTPException(400, tr("Bu to'lov qaytarish kutilayotgan holatda emas"))
        refund = p["refund_amount"] or p["amount"]
        db.execute("UPDATE payments SET status = 'refunded', refund_amount = ? WHERE id = ?", (refund, pid))
        db.execute("UPDATE bookings SET payment_status = 'refunded' WHERE id = ?", (p["booking_id"],))
        notify(db, p["user_id"], "payment_refunded", f"/receipt.html?payment={pid}", total=refund)
        audit(db, request, "payment_refunded", "payment", pid, amount=refund)
    return ok()


@require("admin")
async def admin_payout(request: Request):
    data = await parse_body(request, PayoutIn)
    with get_db() as db:
        bal = owner_balance(db, data.owner_id)
        if data.amount > bal["available"]:
            raise HTTPException(400, tr("Summa owner balansidan katta"))
        db.execute("INSERT INTO payouts (owner_id, amount, note, created_by) VALUES (?, ?, ?, ?)",
                   (data.owner_id, data.amount, data.note, request.state.user["id"]))
        notify(db, data.owner_id, "payout_sent", "/dashboard.html?mode=owner#earnings", total=data.amount)
        audit(db, request, "payout_sent", "user", data.owner_id, amount=data.amount)
        return ok(owner_balance(db, data.owner_id))


# ---------------- Ijarachi: to'lovlar tarixi ----------------
@require()
async def my_payments(request: Request):
    uid = request.state.user["id"]
    with get_db() as db:
        maintain_payments(db)
        items = rows(db.execute(
            """SELECT p.id, p.provider, p.status, p.amount, p.refund_amount, p.created_at, p.paid_at, p.cancelled_at,
                      b.id AS booking_id, b.start_date, b.end_date, b.days, b.status AS booking_status, c.id AS car_id, c.brand, c.model, c.year
               FROM payments p JOIN bookings b ON b.id = p.booking_id JOIN cars c ON c.id = b.car_id
               WHERE p.user_id = ? AND p.status != 'created' ORDER BY p.id DESC LIMIT 200""", (uid,)))
        paid = sum(i["amount"] for i in items if i["status"] in ("paid", "refunded", "refund_pending"))
        refunded = sum(i["refund_amount"] for i in items if i["status"] == "refunded")
        waiting = sum(i["refund_amount"] for i in items if i["status"] == "refund_pending")
    return ok({"items": items, "paid_total": paid, "refunded_total": refunded, "refund_waiting": waiting,
               "policy": [{"min_days": d, "pct": p} for d, p in REFUND_RULES]})


# ---------------- Owner: pul yechish so'rovlari ----------------
@require("user")
async def create_payout_request(request: Request):
    data = await parse_body(request, PayoutRequestIn)
    uid = request.state.user["id"]
    with get_db() as db:
        with transaction(db, immediate=True):
            if db.execute("SELECT 1 FROM payout_requests WHERE owner_id = ? AND status = 'pending'", (uid,)).fetchone():
                raise HTTPException(409, tr("Sizda ko'rib chiqilayotgan so'rov bor. Avval u yakunlansin"))
            bal = owner_balance(db, uid)
            if data.amount > bal["available"]:
                raise HTTPException(400, tr("Summa mavjud balansdan katta: {n}", n=f"{bal['available']:,}".replace(",", " ")))
            cur = db.execute("INSERT INTO payout_requests (owner_id, amount, method, card_last4, note) VALUES (?, ?, ?, ?, ?)",
                             (uid, data.amount, data.method, data.card_last4, data.note))
            for (admin_id,) in db.execute("SELECT id FROM users WHERE role = 'admin' AND is_active = 1").fetchall():
                notify(db, admin_id, "payout_requested", "/admin.html#finance", name=request.state.user["full_name"], total=data.amount)
        return ok({"id": cur.lastrowid, **owner_balance(db, uid)}, 201)


@require("user")
async def cancel_payout_request(request: Request):
    rid, uid = path_int(request), request.state.user["id"]
    with get_db() as db:
        n = db.execute("UPDATE payout_requests SET status = 'cancelled', processed_at = datetime('now') "
                       "WHERE id = ? AND owner_id = ? AND status = 'pending'", (rid, uid)).rowcount
        if not n:
            raise HTTPException(404, tr("So'rov topilmadi"))
        return ok(owner_balance(db, uid))


@require("admin")
async def admin_payout_requests(request: Request):
    with get_db() as db:
        items = rows(db.execute(
            """SELECT r.*, u.full_name, u.email, u.phone FROM payout_requests r JOIN users u ON u.id = r.owner_id
               ORDER BY (r.status = 'pending') DESC, r.id DESC LIMIT 200"""))
        for it in items:
            if it["status"] == "pending":
                it["balance"] = owner_balance(db, it["owner_id"])["balance"]
    return ok({"items": items})


async def _decide(request: Request, approve: bool):
    rid = path_int(request)
    data = await parse_body(request, PayoutDecisionIn)
    if not approve and not data.note:
        raise HTTPException(400, tr("Rad etish sababini yozing"))
    admin = request.state.user
    with get_db() as db:
        with transaction(db, immediate=True):
            r = one(db.execute("SELECT * FROM payout_requests WHERE id = ?", (rid,)))
            if not r:
                raise HTTPException(404, tr("So'rov topilmadi"))
            if r["status"] != "pending":
                raise HTTPException(400, tr("Bu so'rov allaqachon ko'rib chiqilgan"))
            if approve:
                bal = owner_balance(db, r["owner_id"])
                if r["amount"] > bal["balance"]:
                    raise HTTPException(400, tr("Summa owner balansidan katta"))
                note = data.note or ("**** " + r["card_last4"] if r["card_last4"] else r["method"])
                cur = db.execute("INSERT INTO payouts (owner_id, amount, note, created_by) VALUES (?, ?, ?, ?)",
                                 (r["owner_id"], r["amount"], note, admin["id"]))
                db.execute("UPDATE payout_requests SET status = 'paid', payout_id = ?, admin_note = ?, processed_by = ?, "
                           "processed_at = datetime('now') WHERE id = ?", (cur.lastrowid, data.note, admin["id"], rid))
                notify(db, r["owner_id"], "payout_sent", "/dashboard.html?mode=owner#earnings", total=r["amount"])
            else:
                db.execute("UPDATE payout_requests SET status = 'rejected', admin_note = ?, processed_by = ?, "
                           "processed_at = datetime('now') WHERE id = ?", (data.note, admin["id"], rid))
                notify(db, r["owner_id"], "payout_rejected", "/dashboard.html?mode=owner#earnings", total=r["amount"], note=data.note)
            audit(db, request, "payout_request_" + ("paid" if approve else "rejected"), "user", r["owner_id"], amount=r["amount"])
    return ok()


@require("admin")
async def admin_approve_payout_request(request: Request):
    return await _decide(request, True)


@require("admin")
async def admin_reject_payout_request(request: Request):
    return await _decide(request, False)


routes = [
    Route("/api/payments/providers", list_providers, methods=["GET"]),
    Route("/api/my/payments", my_payments, methods=["GET"]),
    Route("/api/my/payout-requests", create_payout_request, methods=["POST"]),
    Route("/api/my/payout-requests/{id:int}/cancel", cancel_payout_request, methods=["POST"]),
    Route("/api/admin/payout-requests", admin_payout_requests, methods=["GET"]),
    Route("/api/admin/payout-requests/{id:int}/approve", admin_approve_payout_request, methods=["POST"]),
    Route("/api/admin/payout-requests/{id:int}/reject", admin_reject_payout_request, methods=["POST"]),
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
    Route("/api/admin/fee-settlements", admin_fee_settlement, methods=["POST"]),
]
