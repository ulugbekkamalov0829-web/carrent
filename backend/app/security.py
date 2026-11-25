"""Xavfsizlik: parol xeshlash (scrypt), JWT, rol va egalik bo'yicha kirish, so'rovlarni cheklash."""
import base64
import re
import functools
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from threading import Lock

import jwt
from starlette.exceptions import HTTPException
from starlette.requests import Request

from .config import settings
from .db import get_db, one
from .i18n import tr

# ---------------- Parollar ----------------
# scrypt — xotiraga og'ir algoritm (OWASP tavsiya qiladi), Python standart kutubxonasida bor.
# Argon2id'ga o'tish: argon2-cffi o'rnatilgach shu ikki funksiyani almashtirish kifoya (xesh prefiksi algoritmni bildiradi).
_N, _R, _P, _DKLEN = 2**14, 8, 1, 64


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return "scrypt${}${}${}${}${}".format(_N, _R, _P, base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(dk_b64)
        dk = hashlib.scrypt(password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


_DUMMY_HASH = hash_password(secrets.token_hex(8))


def burn_time() -> None:
    """Mavjud bo'lmagan email uchun ham xesh hisoblaymiz — javob vaqtidan email borligini bilib bo'lmaydi."""
    verify_password("x", _DUMMY_HASH)


# Eng keng tarqalgan parollar (qisqartirilgan ro'yxat; productionda HIBP k-anonimlik API'si bilan almashtirish mumkin)
COMMON_PASSWORDS = {
    "123456789012", "1234567890123", "qwertyuiop12", "password1234", "parol1234567", "admin1234567",
    "qwerty123456", "111111111111", "000000000000", "123123123123", "iloveyou1234", "abcdefghijkl",
    "passwordpassword", "qwertyqwerty", "1q2w3e4r5t6y", "asdfghjkl123", "zxcvbnm12345", "toshkent2024",
    "tashkent2024", "toshkent2025", "uzbekistan12", "ozbekiston12", "carrent12345", "123456qwerty",
}


# ---------------- Sessiyalar (JWT + bazadagi yozuv) ----------------
# Token ichida tasodifiy jti bor; bazada uning xeshi saqlanadi. Shu tufayli istalgan qurilmadan chiqish,
# "barcha qurilmalardan chiqish" va parol o'zgarganda eski tokenlarni bekor qilish mumkin.
SESSION_TOUCH_SEC = 300


def _jti_hash(jti: str) -> str:
    return hashlib.sha256(jti.encode()).hexdigest()


WEB_SESSION_HOURS = 12   # brauzer (sayt) orqali: qisqa sessiya, brauzer yopilsa — qayta email va parol


def is_app_client(request: Request | None) -> bool:
    """O'rnatilgan ilova (PWA) so'rovi: sessiya uzoq saqlanadi, ekran PIN kod bilan himoyalanadi."""
    return bool(request) and request.headers.get("x-app-mode") == "app"


def create_session(db, user_id: int, role: str, request: Request | None = None) -> str:
    jti = secrets.token_urlsafe(24)
    ua = (request.headers.get("user-agent", "") if request else "")[:200]
    db.execute("INSERT INTO sessions (id, user_id, ip, user_agent) VALUES (?, ?, ?, ?)",
               (_jti_hash(jti), user_id, client_ip(request) if request else None, ua))
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "role": role, "jti": jti, "iat": now,
               "exp": now + timedelta(hours=settings.TOKEN_TTL_HOURS if is_app_client(request) or request is None else WEB_SESSION_HOURS)}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def revoke_user_sessions(db, user_id: int, except_sid: str | None = None) -> int:
    sql, params = "UPDATE sessions SET revoked_at = datetime('now') WHERE user_id = ? AND revoked_at IS NULL", [user_id]
    if except_sid:
        sql += " AND id != ?"; params.append(except_sid)
    return db.execute(sql, params).rowcount


def set_auth_cookie(response, token: str, persistent: bool = True) -> None:
    """Ilovada — 7 kunlik cookie; saytda (brauzerda) — sessiya cookie: brauzer yopilishi bilan o'chadi."""
    response.set_cookie(settings.COOKIE_NAME, token, max_age=settings.TOKEN_TTL_HOURS * 3600 if persistent else None, httponly=True,
                        secure=settings.COOKIE_SECURE, samesite="lax", path="/")


def clear_auth_cookie(response) -> None:
    response.delete_cookie(settings.COOKIE_NAME, path="/")


PUBLIC_USER_FIELDS = ("id, full_name, email, phone, region, district, role, active_mode, lang, is_active, created_at, "
                      "email_verified, phone_verified, avatar, show_phone, marketing_ok, notify_prefs, must_change_pw")


def _token(request: Request) -> str | None:
    token = request.cookies.get(settings.COOKIE_NAME)
    if not token:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:]
    return token


def current_user_or_none(request: Request) -> dict | None:
    token = _token(request)
    if not token:
        return None
    payload = decode_token(token)
    if not payload or "jti" not in payload:
        return None
    sid = _jti_hash(payload["jti"])
    # Har so'rovda bazadan tekshiramiz: bekor qilingan sessiya yoki bloklangan foydalanuvchi darhol chiqariladi
    with get_db() as db:
        sess = one(db.execute("SELECT user_id, revoked_at, last_seen FROM sessions WHERE id = ?", (sid,)))
        if not sess or sess["revoked_at"] or sess["user_id"] != int(payload["sub"]):
            return None
        user = one(db.execute(f"SELECT {PUBLIC_USER_FIELDS} FROM users WHERE id = ?", (sess["user_id"],)))
        if not user or not user["is_active"]:
            return None
        if (datetime.now(timezone.utc).replace(tzinfo=None) - datetime.fromisoformat(sess["last_seen"])).total_seconds() > SESSION_TOUCH_SEC:
            db.execute("UPDATE sessions SET last_seen = datetime('now') WHERE id = ?", (sid,))
    user["session_id"] = sid
    return user


# ---------------- Telefon raqami ----------------
def normalize_phone(raw: str | None) -> str | None:
    """+998 90 123-45-67, 998901234567, 901234567 -> +998901234567. Noto'g'ri bo'lsa None."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 9:
        digits = "998" + digits
    if not 9 <= len(digits) <= 15:
        return None
    if digits.startswith("998") and len(digits) != 12:
        return None
    return "+" + digits


# ---------------- Bir martalik kodlar ----------------
def new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(code: str, purpose: str, target: str) -> str:
    """Kod ochiq saqlanmaydi: maxfiy kalit bilan HMAC (baza o'g'irlansa ham kodni tiklab bo'lmaydi)."""
    msg = f"{purpose}|{target.lower()}|{code}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()


def require(*roles: str):
    """Dekorator: tizimga kirganlikni va (berilgan bo'lsa) rolni tekshiradi.
    Owner amallari uchun rol emas, egalik tekshiriladi (marshrut ichida)."""
    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(request: Request):
            user = current_user_or_none(request)
            if not user:
                raise HTTPException(401, tr("Avval tizimga kiring"))
            if roles and user["role"] not in roles:
                raise HTTPException(403, tr("Bu amal uchun huquqingiz yo'q"))
            request.state.user = user
            return await fn(request)
        return wrapper
    return decorator


def client_ip(request: Request | None) -> str:
    """X-Forwarded-For sarlavhasiga ko'r-ko'rona ishonmaymiz (soxtalashtirib limitni aylanib o'tish mumkin).
    Proksi ortida ishlaganda uvicorn --proxy-headers haqiqiy IP'ni request.client ga o'zi yozadi."""
    return request.client.host if request and request.client else "?"


# ---------------- So'rovlarni cheklash ----------------
class RateLimiter:
    def __init__(self, limit: int, window: int):
        self.limit, self.window = limit, window
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = Lock()

    def hit(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)


login_limiter = RateLimiter(settings.LOGIN_ATTEMPTS, settings.LOGIN_WINDOW_SEC)
account_limiter = RateLimiter(20, 900)       # bitta akkauntga turli IP'lardan: 15 daqiqada 20 urinish
code_limiter = RateLimiter(10, 900)          # kod tekshirish urinishlari (IP bo'yicha)
forgot_limiter = RateLimiter(5, 900)         # parolni tiklash so'rovlari (IP bo'yicha)
register_limiter = RateLimiter(settings.REGISTER_PER_HOUR, 3600)  # bir IP'dan soatiga N ta ro'yxat
message_limiter = RateLimiter(30, 60)         # spamga qarshi: daqiqasiga 30 ta xabar
