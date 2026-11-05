"""Ilova ekran qulfi (PIN kod) — bank ilovalaridagidek.

O'rnatilgan ilova (telefon yoki kompyuter) har ochilganda PIN kod yoki barmoq izi so'raydi.
PIN har bir qurilma uchun alohida saqlanadi (faqat xesh). 5 marta xato kiritilsa — PIN o'chadi,
shu qurilmadagi sessiya yopiladi va email + parol bilan qayta kirish kerak bo'ladi.
"""
import re

from pydantic import Field
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.routing import Route

from ..config import settings
from ..db import get_db, one
from ..i18n import tr
from ..schemas import Base
from ..security import clear_auth_cookie, hash_password, require, verify_password
from ..utils import ok, parse_body

MAX_FAILS = 5
DEV_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


class PinIn(Base):
    device_id: str = Field(min_length=16, max_length=64)
    pin: str = Field(min_length=4, max_length=6)


class DeviceIn(Base):
    device_id: str = Field(min_length=16, max_length=64)


def _check_device(dev: str) -> str:
    if not DEV_RE.match(dev):
        raise HTTPException(400, tr("Qurilma aniqlanmadi"))
    return dev


def weak_pin(pin: str) -> bool:
    """1111, 1234, 4321 kabi oson topiladigan kodlar qabul qilinmaydi."""
    if len(set(pin)) == 1:
        return True
    d = [int(c) for c in pin]
    steps = {b - a for a, b in zip(d, d[1:])}
    return steps in ({1}, {-1})


@require()
async def pin_status(request: Request):
    dev = _check_device(request.query_params.get("device_id", ""))
    with get_db() as db:
        row = one(db.execute("SELECT created_at FROM app_pins WHERE user_id = ? AND device_id = ?", (request.state.user["id"], dev)))
    return ok({"set": bool(row), "created_at": row["created_at"] if row else None})


@require()
async def pin_set(request: Request):
    data = await parse_body(request, PinIn)
    dev = _check_device(data.device_id)
    if not re.fullmatch(r"\d{4,6}", data.pin):
        raise HTTPException(400, tr("PIN kod 4 ta raqamdan iborat bo'lishi kerak"))
    if weak_pin(data.pin):
        raise HTTPException(400, tr("Bu PIN kodni topish oson (1111, 1234 kabi). Boshqasini tanlang"))
    with get_db() as db:
        db.execute("INSERT INTO app_pins (user_id, device_id, pin_hash) VALUES (?, ?, ?) "
                   "ON CONFLICT(user_id, device_id) DO UPDATE SET pin_hash = excluded.pin_hash, fails = 0, created_at = datetime('now')",
                   (request.state.user["id"], dev, hash_password(data.pin)))
    return ok({"set": True})


@require()
async def pin_verify(request: Request):
    data = await parse_body(request, PinIn)
    dev = _check_device(data.device_id)
    u = request.state.user
    with get_db() as db:
        row = one(db.execute("SELECT pin_hash, fails FROM app_pins WHERE user_id = ? AND device_id = ?", (u["id"], dev)))
        if not row:
            raise HTTPException(404, tr("Bu qurilmada PIN kod o'rnatilmagan"))
        if verify_password(data.pin, row["pin_hash"]):
            db.execute("UPDATE app_pins SET fails = 0 WHERE user_id = ? AND device_id = ?", (u["id"], dev))
            return ok({"unlocked": True})
        fails = row["fails"] + 1
        if fails >= MAX_FAILS:
            # Juda ko'p xato: PIN o'chadi, sessiya yopiladi — faqat email va parol bilan qayta kirish
            db.execute("DELETE FROM app_pins WHERE user_id = ? AND device_id = ?", (u["id"], dev))
            db.execute("UPDATE sessions SET revoked_at = datetime('now') WHERE id = ?", (u["session_id"],))
            resp = ok({"unlocked": False, "locked_out": True, "detail": tr("PIN kod 5 marta noto'g'ri kiritildi. Email va parol bilan qayta kiring")}, 403)
            clear_auth_cookie(resp)
            return resp
        db.execute("UPDATE app_pins SET fails = ? WHERE user_id = ? AND device_id = ?", (fails, u["id"], dev))
    raise HTTPException(401, tr("PIN kod noto'g'ri. Yana {n} ta urinish qoldi", n=MAX_FAILS - fails))


class ForgotIn(Base):
    channel: str = Field(pattern="^(email|sms)$")


class ForgotConfirmIn(Base):
    device_id: str = Field(min_length=16, max_length=64)
    code: str | None = Field(default=None, max_length=8)
    password: str | None = Field(default=None, max_length=128)


@require()
async def pin_forgot(request: Request):
    """PIN esdan chiqdi: emailga yoki (tasdiqlangan) telefonga kod yuboriladi."""
    from .. import channels
    from .auth import _issue_code
    data = await parse_body(request, ForgotIn)
    uid = request.state.user["id"]
    with get_db() as db:
        u = one(db.execute("SELECT id, email, phone_norm, phone_verified, lang FROM users WHERE id = ?", (uid,)))
        if data.channel == "sms" and not (u["phone_norm"] and u["phone_verified"]):
            raise HTTPException(400, tr("Telefon raqamingiz tasdiqlanmagan. Email orqali tiklang"))
        target = u["email"] if data.channel == "email" else u["phone_norm"]
        try:
            _issue_code(db, u, "reset", data.channel, target, template="pin_reset")
        except channels.DeliveryUnavailable:
            raise HTTPException(503, tr("Hozir kod yuborib bo'lmadi. Parolingiz bilan tiklang"))
    masked = target[:2] + "***" + target[target.find("@"):] if data.channel == "email" else target[:6] + "***" + target[-2:]
    return ok({"sent": True, "to": masked, "ttl_sec": 60 * settings.CODE_TTL_MIN})


@require()
async def pin_forgot_confirm(request: Request):
    """Kod (email/SMS) yoki akkaunt paroli to'g'ri bo'lsa — eski PIN o'chadi, foydalanuvchi yangisini o'rnatadi."""
    from ..security import code_limiter, client_ip
    from .auth import _check_code
    data = await parse_body(request, ForgotConfirmIn)
    dev = _check_device(data.device_id)
    u = request.state.user
    if not code_limiter.hit(client_ip(request)):
        raise HTTPException(429, tr("Juda ko'p urinish. 5 daqiqadan so'ng qayta urinib ko'ring"))
    with get_db() as db:
        if data.password:
            row = one(db.execute("SELECT password_hash FROM users WHERE id = ?", (u["id"],)))
            if not verify_password(data.password, row["password_hash"]):
                raise HTTPException(400, tr("Parol noto'g'ri"))
        elif data.code:
            _check_code(db, u["id"], "reset", data.code)
        else:
            raise HTTPException(400, tr("Kodni yoki parolni kiriting"))
        db.execute("DELETE FROM app_pins WHERE user_id = ? AND device_id = ?", (u["id"], dev))
    return ok({"reset": True})


@require()
async def pin_delete(request: Request):
    data = await parse_body(request, DeviceIn)
    with get_db() as db:
        db.execute("DELETE FROM app_pins WHERE user_id = ? AND device_id = ?", (request.state.user["id"], _check_device(data.device_id)))
    return ok({"set": False})


routes = [
    Route("/api/me/pin", pin_status, methods=["GET"]),
    Route("/api/me/pin", pin_set, methods=["PUT"]),
    Route("/api/me/pin/verify", pin_verify, methods=["POST"]),
    Route("/api/me/pin/delete", pin_delete, methods=["POST"]),
    Route("/api/me/pin/forgot", pin_forgot, methods=["POST"]),
    Route("/api/me/pin/forgot/confirm", pin_forgot_confirm, methods=["POST"]),
]
