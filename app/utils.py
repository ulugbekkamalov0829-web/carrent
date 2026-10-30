"""Umumiy yordamchi funksiyalar."""
import json
from datetime import date

from pydantic import BaseModel, ValidationError
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

from .i18n import tr


class ApiValidationError(Exception):
    def __init__(self, errors: list[dict]):
        self.errors = errors


def _message(err: dict) -> str:
    t, ctx = err.get("type", ""), err.get("ctx") or {}
    if t == "value_error":
        return tr(str(ctx.get("error", err.get("msg"))))
    if t == "missing":
        return tr("Majburiy maydon")
    if t == "string_too_short":
        return tr("Kamida {n} ta belgi bo'lishi kerak", n=ctx.get("min_length"))
    if t == "string_too_long":
        return tr("Ko'pi bilan {n} ta belgi bo'lishi mumkin", n=ctx.get("max_length"))
    if t in ("greater_than_equal", "greater_than"):
        return tr("Qiymat {n} dan kichik bo'lmasligi kerak", n=ctx.get("ge", ctx.get("gt")))
    if t in ("less_than_equal", "less_than"):
        return tr("Qiymat {n} dan katta bo'lmasligi kerak", n=ctx.get("le", ctx.get("lt")))
    if t == "literal_error":
        return tr("Ruxsat etilgan qiymatlardan birini tanlang")
    if t.startswith("int") or t.startswith("float"):
        return tr("Son kiritilishi kerak")
    if t.startswith("date"):
        return tr("Sana noto'g'ri (YYYY-MM-DD)")
    if t == "string_pattern_mismatch":
        if "card_last4" in (err.get("loc") or ()):
            return tr("Karta raqamining oxirgi 4 raqamini kiriting")
        return tr("Kod 6 ta raqamdan iborat bo'lishi kerak")
    if t == "extra_forbidden":
        return tr("Ortiqcha maydon")
    return tr("Qiymat noto'g'ri")


def validation_errors(exc: ValidationError) -> list[dict]:
    return [{"field": str(e["loc"][0]) if e.get("loc") else "", "msg": _message(e)} for e in exc.errors()]


async def parse_body(request: Request, model: type[BaseModel]):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(400, tr("So'rov tanasi JSON formatida bo'lishi kerak"))
    if not isinstance(data, dict):
        raise HTTPException(400, tr("So'rov tanasi obyekt bo'lishi kerak"))
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ApiValidationError(validation_errors(exc))


def path_int(request: Request, name: str = "id") -> int:
    return int(request.path_params[name])


def q_int(request: Request, name: str, default=None, lo=None, hi=None):
    raw = request.query_params.get(name)
    if raw in (None, ""):
        return default
    try:
        val = int(raw)
    except ValueError:
        raise HTTPException(400, tr("'{name}' parametri son bo'lishi kerak", name=name))
    if lo is not None:
        val = max(lo, val)
    if hi is not None:
        val = min(hi, val)
    return val


def q_date(request: Request, name: str):
    raw = request.query_params.get(name)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise HTTPException(400, tr("'{name}' sana formati YYYY-MM-DD bo'lishi kerak", name=name))


def q_str(request: Request, name: str, max_len: int = 60):
    raw = (request.query_params.get(name) or "").strip()
    return raw[:max_len] or None


def ok(data=None, status: int = 200) -> JSONResponse:
    return JSONResponse(data if data is not None else {"ok": True}, status_code=status)


def today() -> date:
    return date.today()


def notify(db, user_id: int, type_: str, link: str = "", **params) -> None:
    """Bildirishnoma kod + parametrlar bilan saqlanadi; matnni frontend foydalanuvchi tilida chiqaradi.
    Foydalanuvchi sozlamalarida yoqilgan bo'lsa, email/SMS'ga ham nusxa yuboriladi."""
    db.execute("INSERT INTO notifications (user_id, type, params, link) VALUES (?, ?, ?, ?)",
               (user_id, type_, json.dumps(params, ensure_ascii=False), link))
    from .channels import mirror_notification
    try:
        mirror_notification(db, user_id, type_, params, link)
    except Exception:  # bildirishnoma nusxasi asosiy amalni hech qachon buzmasin
        pass


def audit(db, request: Request, action: str, target_type: str = "", target_id: int | None = None, **details) -> None:
    from .security import client_ip
    actor = getattr(request.state, "user", None)
    db.execute("INSERT INTO audit_logs (actor_id, action, target_type, target_id, details, ip) VALUES (?, ?, ?, ?, ?, ?)",
               (actor["id"] if actor else None, action, target_type, target_id,
                json.dumps(details, ensure_ascii=False) if details else None, client_ip(request)))


def complete_finished_bookings(db) -> None:
    """Tugash sanasi o'tgan tasdiqlangan bronlarni 'yakunlangan' holatiga o'tkazadi."""
    db.execute("UPDATE bookings SET status = 'completed', updated_at = datetime('now') "
               "WHERE status = 'approved' AND end_date < ?", (today().isoformat(),))


def car_title(car: dict) -> str:
    return f"{car['brand']} {car['model']} {car['year']}"


def bps_split(total: int, bps: int) -> tuple[int, int]:
    """Komissiya: butun so'mda, yarim yuqoriga yaxlitlanadi. (komissiya, owner ulushi) qaytaradi; yig'indisi = total."""
    commission = (total * bps + 5000) // 10000
    return commission, total - commission
