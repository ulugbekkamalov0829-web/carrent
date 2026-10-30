"""Akkaunt: ro'yxatdan o'tish, kirish (email yoki telefon), sessiyalar, parolni tiklash, tasdiqlash, sozlamalar."""
import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.routing import Route

from .. import channels
from ..config import settings
from ..db import get_db, one, rows, transaction
from ..i18n import tr
from ..schemas import (CodeIn, EmailChangeIn, ForgotIn, LangIn, LoginIn, ModeIn, PasswordChangeIn, PasswordConfirmIn,
                       PrefsIn, ProfileIn, RegisterIn, ResetIn, VerifyConfirmIn, VerifyStartIn)
from ..security import (PUBLIC_USER_FIELDS, account_limiter, burn_time, clear_auth_cookie, client_ip, code_limiter,
                        create_session, current_user_or_none, forgot_limiter, hash_code, hash_password, login_limiter,
                        new_code, normalize_phone, register_limiter, require, revoke_user_sessions, set_auth_cookie,
                        verify_password)
from ..utils import audit, notify, ok, parse_body

DEFAULT_PREFS = {"email_booking": True, "email_messages": False, "sms_booking": False}


def user_payload(db, uid: int) -> dict:
    user = one(db.execute(f"SELECT {PUBLIC_USER_FIELDS} FROM users WHERE id = ?", (uid,)))
    user["cars_count"] = db.execute("SELECT COUNT(*) FROM cars WHERE owner_id = ?", (uid,)).fetchone()[0]
    user["notify_prefs"] = {**DEFAULT_PREFS, **json.loads(user.get("notify_prefs") or "{}")}
    for k in ("email_verified", "phone_verified", "show_phone", "marketing_ok"):
        user[k] = bool(user[k])
    return user


def _find_by_login(db, login: str) -> dict | None:
    """Email yoki telefon bo'yicha qidirish."""
    login = login.strip()
    if "@" in login:
        return one(db.execute("SELECT * FROM users WHERE email = ? AND deleted_at IS NULL", (login.lower(),)))
    phone = normalize_phone(login)
    if not phone:
        return None
    return one(db.execute("SELECT * FROM users WHERE phone_norm = ? AND deleted_at IS NULL", (phone,)))


def _login_response(db, user_id: int, role: str, request: Request, status: int = 200):
    token = create_session(db, user_id, role, request)
    resp = ok({"user": user_payload(db, user_id)}, status)
    set_auth_cookie(resp, token)
    return resp


def security_event(db, request: Request, user: dict, what_key: str) -> None:
    """Muhim o'zgarish: sayt ichida bildirishnoma + emailga xat + audit jurnali."""
    notify(db, user["id"], "security", "/settings.html#security", what=what_key)
    audit(db, request, what_key, "user", user["id"])
    try:
        channels.send("email", user["email"], "security", user.get("lang") or "uz", what=_what_text(what_key, user.get("lang")))
    except channels.DeliveryUnavailable:
        pass


def _what_text(key: str, lang: str | None) -> str:
    texts = {"password_changed": ("parol o‘zgartirildi", "пароль изменён", "your password was changed"),
             "password_reset": ("parol tiklandi", "пароль восстановлен", "your password was reset"),
             "email_changed": ("email manzil o‘zgartirildi", "email изменён", "your email was changed"),
             "sessions_revoked": ("barcha qurilmalardan chiqildi", "выполнен выход со всех устройств", "signed out of all devices")}
    t = texts.get(key, (key, key, key))
    return t[{"ru": 1, "en": 2}.get(lang or "uz", 0)]


# ---------------- Ro'yxatdan o'tish va kirish ----------------
async def register(request: Request):
    data = await parse_body(request, RegisterIn)
    if not register_limiter.hit(client_ip(request)):
        raise HTTPException(429, tr("Juda ko'p urinish. 5 daqiqadan so'ng qayta urinib ko'ring"))
    with get_db() as db:
        if db.execute("SELECT 1 FROM users WHERE phone_norm = ?", (data.phone,)).fetchone():
            raise HTTPException(409, tr("Bu telefon raqam bilan allaqachon ro'yxatdan o'tilgan"))
        try:
            cur = db.execute(
                "INSERT INTO users (full_name, email, phone, phone_norm, password_hash, lang, marketing_ok, region, district) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (data.full_name, data.email, data.phone, data.phone, hash_password(data.password), data.lang, int(data.marketing_ok),
                 data.region, data.district))
        except sqlite3.IntegrityError:
            raise HTTPException(409, tr("Bu email bilan allaqachon ro'yxatdan o'tilgan"))
        uid = cur.lastrowid
        # Emailni tasdiqlash kodi darhol yuboriladi (tasdiqlash ixtiyoriy, lekin profilda belgi ko'rinadi)
        try:
            _issue_code(db, {"id": uid, "lang": data.lang}, "verify_email", "email", data.email)
        except (channels.DeliveryUnavailable, HTTPException):
            pass
        return _login_response(db, uid, "user", request, 201)


async def login(request: Request):
    data = await parse_body(request, LoginIn)
    ident = data.identifier.lower()
    if not ident:
        raise HTTPException(401, tr("Login yoki parol noto'g'ri"))
    if not login_limiter.hit(f"{client_ip(request)}|{ident}") or not account_limiter.hit(ident):
        raise HTTPException(429, tr("Juda ko'p urinish. 5 daqiqadan so'ng qayta urinib ko'ring"))
    with get_db() as db:
        row = _find_by_login(db, ident)
        if not row:
            burn_time()
            raise HTTPException(401, tr("Login yoki parol noto'g'ri"))
        if not verify_password(data.password, row["password_hash"]):
            raise HTTPException(401, tr("Login yoki parol noto'g'ri"))
        if not row["is_active"]:
            raise HTTPException(403, tr("Hisobingiz administrator tomonidan bloklangan"))
        login_limiter.reset(f"{client_ip(request)}|{ident}")
        return _login_response(db, row["id"], row["role"], request)


async def logout(request: Request):
    user = current_user_or_none(request)
    if user:
        with get_db() as db:
            db.execute("UPDATE sessions SET revoked_at = datetime('now') WHERE id = ?", (user["session_id"],))
    resp = ok()
    clear_auth_cookie(resp)
    return resp


async def me(request: Request):
    user = current_user_or_none(request)
    if user:
        with get_db() as db:
            user = user_payload(db, user["id"])
    return ok({"user": user})


# ---------------- Bir martalik kodlar ----------------
def _issue_code(db, user: dict, purpose: str, channel: str, target: str) -> str:
    """Kod yaratib yuboradi. Qayta yuborish 60 soniyadan keyin, kuniga ko'pi bilan N ta."""
    last = one(db.execute("SELECT created_at FROM verification_codes WHERE user_id = ? AND purpose = ? ORDER BY id DESC LIMIT 1",
                          (user["id"], purpose)))
    if last:
        age = (datetime.now(timezone.utc).replace(tzinfo=None) - datetime.fromisoformat(last["created_at"])).total_seconds()
        if age < settings.CODE_RESEND_SEC:
            raise HTTPException(429, tr("Kodni qayta yuborish uchun {n} soniya kuting", n=int(settings.CODE_RESEND_SEC - age) + 1))
    day = db.execute("SELECT COUNT(*) FROM verification_codes WHERE user_id = ? AND created_at >= datetime('now', '-1 day')",
                     (user["id"],)).fetchone()[0]
    if day >= settings.CODES_PER_DAY:
        raise HTTPException(429, tr("Bugun juda ko'p kod so'raldi. Ertaga qayta urinib ko'ring"))
    code = new_code()
    # Oldingi ishlatilmagan kodlar bekor qilinadi — faqat oxirgisi amal qiladi
    db.execute("UPDATE verification_codes SET used_at = datetime('now') WHERE user_id = ? AND purpose = ? AND used_at IS NULL",
               (user["id"], purpose))
    expires = (datetime.now(timezone.utc) + timedelta(minutes=settings.CODE_TTL_MIN)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute("INSERT INTO verification_codes (user_id, purpose, channel, target, code_hash, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
               (user["id"], purpose, channel, target, hash_code(code, purpose, target), expires))
    template = "verify_phone" if channel == "sms" and purpose != "reset" else purpose
    return channels.send(channel, target, template, user.get("lang") or "uz", db=db, code=code, ttl=settings.CODE_TTL_MIN)


def _check_code(db, user_id: int, purpose: str, code: str) -> dict:
    """Kodni tekshiradi: muddat, urinishlar soni, bir martalik. Muvaffaqiyatda kod yozuvini qaytaradi.
    MUHIM: tranzaksiyadan TASHQARIDA chaqiriladi — aks holda xato urinishlar hisobi ROLLBACK bilan o'chib ketadi."""
    rec = one(db.execute("SELECT * FROM verification_codes WHERE user_id = ? AND purpose = ? AND used_at IS NULL "
                         "ORDER BY id DESC LIMIT 1", (user_id, purpose)))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if not rec or datetime.fromisoformat(rec["expires_at"]) < now or rec["attempts"] >= settings.CODE_MAX_ATTEMPTS:
        raise HTTPException(400, tr("Kod noto'g'ri yoki muddati tugagan. Yangi kod so'rang"))
    import hmac as _h
    if not _h.compare_digest(rec["code_hash"], hash_code(code, purpose, rec["target"])):
        db.execute("UPDATE verification_codes SET attempts = attempts + 1 WHERE id = ?", (rec["id"],))
        left = settings.CODE_MAX_ATTEMPTS - rec["attempts"] - 1
        raise HTTPException(400, tr("Kod noto'g'ri. Qolgan urinishlar: {n}", n=max(0, left)))
    # Bir martalik: parallel ikki so'rovdan faqat bittasi kodni "ishlatadi"
    if not db.execute("UPDATE verification_codes SET used_at = datetime('now') WHERE id = ? AND used_at IS NULL",
                      (rec["id"],)).rowcount:
        raise HTTPException(400, tr("Kod noto'g'ri yoki muddati tugagan. Yangi kod so'rang"))
    return rec


# ---------------- Parolni tiklash (email yoki telefon) ----------------
GENERIC_SENT = "Agar bunday akkaunt mavjud bo'lsa, tasdiqlash kodi yuborildi"


async def forgot(request: Request):
    """Javob har doim bir xil — akkaunt mavjudligini bilib olib bo'lmaydi."""
    data = await parse_body(request, ForgotIn)
    if not forgot_limiter.hit(client_ip(request)):
        raise HTTPException(429, tr("Juda ko'p urinish. 5 daqiqadan so'ng qayta urinib ko'ring"))
    channel = "email" if "@" in data.login else "sms"
    if not channels.channel_available(channel):
        raise HTTPException(503, tr("Parolni tiklash xizmati hozircha sozlanmagan. Administratorga murojaat qiling"))
    via = None
    with get_db() as db:
        user = _find_by_login(db, data.login)
        target = (user["email"] if channel == "email" else user["phone_norm"]) if user else None
        if user and user["is_active"] and target:
            try:
                via = _issue_code(db, user, "reset", channel, target)
            except HTTPException as exc:
                if exc.status_code != 429:
                    raise
                via = "throttled"
        else:
            burn_time()
    result = {"message": tr(GENERIC_SENT), "channel": channel, "ttl_min": settings.CODE_TTL_MIN}
    if settings.DEV_INBOX:
        result["dev_inbox"] = True   # demo: kod test pochta qutisida ko'rinadi
    return ok(result)


async def reset_password(request: Request):
    data = await parse_body(request, ResetIn)
    if not code_limiter.hit(client_ip(request)):
        raise HTTPException(429, tr("Juda ko'p urinish. 5 daqiqadan so'ng qayta urinib ko'ring"))
    with get_db() as db:
        user = _find_by_login(db, data.login)
        if not user:
            raise HTTPException(400, tr("Kod noto'g'ri yoki muddati tugagan. Yangi kod so'rang"))
        rec = _check_code(db, user["id"], "reset", data.code)
        with transaction(db, immediate=True):
            db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(data.new_password), user["id"]))
            # Kod qaysi kanalga kelgan bo'lsa, o'sha kanal tasdiqlangan hisoblanadi
            db.execute(f"UPDATE users SET {'email_verified' if rec['channel'] == 'email' else 'phone_verified'} = 1 WHERE id = ?",
                       (user["id"],))
            revoke_user_sessions(db, user["id"])   # o'g'irlangan sessiyalar ham yopiladi
        security_event(db, request, user, "password_reset")
        return _login_response(db, user["id"], user["role"], request)


# ---------------- Email / telefonni tasdiqlash ----------------
@require()
async def verify_start(request: Request):
    data = await parse_body(request, VerifyStartIn)
    u = request.state.user
    target = u["email"] if data.channel == "email" else normalize_phone(u["phone"])
    if not target:
        raise HTTPException(400, tr("Telefon raqam noto'g'ri"))
    purpose = "verify_email" if data.channel == "email" else "verify_phone"
    with get_db() as db:
        try:
            via = _issue_code(db, u, purpose, data.channel, target)
        except channels.DeliveryUnavailable:
            raise HTTPException(503, tr("Bu kanal orqali yuborish hozircha sozlanmagan"))
    return ok({"sent_to": channels.mask(target), "via": via, "ttl_min": settings.CODE_TTL_MIN})


@require()
async def verify_confirm(request: Request):
    data = await parse_body(request, VerifyConfirmIn)
    u = request.state.user
    if not code_limiter.hit(client_ip(request)):
        raise HTTPException(429, tr("Juda ko'p urinish. 5 daqiqadan so'ng qayta urinib ko'ring"))
    purpose, col = ("verify_email", "email_verified") if data.channel == "email" else ("verify_phone", "phone_verified")
    with get_db() as db:
        _check_code(db, u["id"], purpose, data.code)
        db.execute(f"UPDATE users SET {col} = 1 WHERE id = ?", (u["id"],))
        return ok({"user": user_payload(db, u["id"])})


# ---------------- Profil va sozlamalar ----------------
@require()
async def update_me(request: Request):
    data = await parse_body(request, ProfileIn)
    uid = request.state.user["id"]
    with get_db() as db:
        old = one(db.execute("SELECT phone_norm FROM users WHERE id = ?", (uid,)))
        if data.phone != old["phone_norm"] and db.execute("SELECT 1 FROM users WHERE phone_norm = ? AND id != ?",
                                                          (data.phone, uid)).fetchone():
            raise HTTPException(409, tr("Bu telefon raqam bilan allaqachon ro'yxatdan o'tilgan"))
        changed_phone = data.phone != old["phone_norm"]
        db.execute("UPDATE users SET full_name = ?, phone = ?, phone_norm = ?, region = ?, district = ?, phone_verified = "
                   "CASE WHEN ? THEN 0 ELSE phone_verified END WHERE id = ?",
                   (data.full_name, data.phone, data.phone, data.region, data.district, int(changed_phone), uid))
        return ok({"user": user_payload(db, uid)})


@require()
async def update_prefs(request: Request):
    data = await parse_body(request, PrefsIn)
    uid = request.state.user["id"]
    prefs = {"email_booking": data.email_booking, "email_messages": data.email_messages, "sms_booking": data.sms_booking}
    with get_db() as db:
        db.execute("UPDATE users SET show_phone = ?, marketing_ok = ?, notify_prefs = ? WHERE id = ?",
                   (int(data.show_phone), int(data.marketing_ok), json.dumps(prefs), uid))
        return ok({"user": user_payload(db, uid)})


@require()
async def change_password(request: Request):
    data = await parse_body(request, PasswordChangeIn)
    u = request.state.user
    with get_db() as db:
        row = one(db.execute("SELECT password_hash FROM users WHERE id = ?", (u["id"],)))
        if not verify_password(data.old_password, row["password_hash"]):
            raise HTTPException(400, tr("Eski parol noto'g'ri"))
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(data.new_password), u["id"]))
        # Boshqa barcha qurilmalardagi sessiyalar yopiladi, joriy qurilma qoladi
        revoke_user_sessions(db, u["id"], except_sid=u["session_id"])
        security_event(db, request, u, "password_changed")
    return ok()


@require()
async def email_change_start(request: Request):
    data = await parse_body(request, EmailChangeIn)
    u = request.state.user
    with get_db() as db:
        row = one(db.execute("SELECT password_hash FROM users WHERE id = ?", (u["id"],)))
        if not verify_password(data.password, row["password_hash"]):
            raise HTTPException(400, tr("Parol noto'g'ri"))
        if db.execute("SELECT 1 FROM users WHERE email = ? AND id != ?", (data.new_email, u["id"])).fetchone():
            raise HTTPException(409, tr("Bu email bilan allaqachon ro'yxatdan o'tilgan"))
        try:
            via = _issue_code(db, u, "change_email", "email", data.new_email)
        except channels.DeliveryUnavailable:
            raise HTTPException(503, tr("Bu kanal orqali yuborish hozircha sozlanmagan"))
    return ok({"sent_to": channels.mask(data.new_email), "via": via})


@require()
async def email_change_confirm(request: Request):
    data = await parse_body(request, CodeIn)
    u = request.state.user
    with get_db() as db:
        rec = _check_code(db, u["id"], "change_email", data.code)
        try:
            db.execute("UPDATE users SET email = ?, email_verified = 1 WHERE id = ?", (rec["target"], u["id"]))
        except sqlite3.IntegrityError:
            raise HTTPException(409, tr("Bu email bilan allaqachon ro'yxatdan o'tilgan"))
        security_event(db, request, u, "email_changed")   # xabar eski manzilga ham boradi (u["email"])
        return ok({"user": user_payload(db, u["id"])})


@require()
async def set_mode(request: Request):
    """Rejim faqat interfeys holati. Idempotent; hech qanday ma'lumot ko'chirilmaydi yoki o'chirilmaydi."""
    data = await parse_body(request, ModeIn)
    uid = request.state.user["id"]
    with get_db() as db:
        db.execute("UPDATE users SET active_mode = ? WHERE id = ? AND active_mode != ?", (data.mode, uid, data.mode))
        return ok({"user": user_payload(db, uid)})


async def set_lang(request: Request):
    data = await parse_body(request, LangIn)
    user = current_user_or_none(request)
    if user:
        with get_db() as db:
            db.execute("UPDATE users SET lang = ? WHERE id = ?", (data.lang, user["id"]))
    resp = ok({"lang": data.lang})
    resp.set_cookie("lang", data.lang, max_age=365 * 86400, samesite="lax", path="/")
    return resp


@require()
async def avatar(request: Request):
    from .cars import reencode_image, _image_ext
    uid = request.state.user["id"]
    async with request.form(max_files=1, max_fields=2) as form:
        f = form.get("avatar")
        if not f or not hasattr(f, "read"):
            raise HTTPException(400, tr("Rasm tanlanmagan"))
        content = await f.read(settings.MAX_IMAGE_MB * 1024 * 1024 + 1)
    if len(content) > settings.MAX_IMAGE_MB * 1024 * 1024:
        raise HTTPException(413, tr("Har bir rasm {n} MB dan oshmasligi kerak", n=settings.MAX_IMAGE_MB))
    if not _image_ext(content[:16]):
        raise HTTPException(400, tr("Faqat JPG, PNG yoki WEBP rasm yuklash mumkin"))
    try:
        clean = reencode_image(content, max_side=320, square=True)
    except ValueError:
        raise HTTPException(400, tr("Faqat JPG, PNG yoki WEBP rasm yuklash mumkin"))
    name = "av_" + secrets.token_hex(12) + ".jpg"
    (settings.UPLOAD_DIR / name).write_bytes(clean)
    with get_db() as db:
        old = db.execute("SELECT avatar FROM users WHERE id = ?", (uid,)).fetchone()[0]
        db.execute("UPDATE users SET avatar = ? WHERE id = ?", ("/uploads/" + name, uid))
        user = user_payload(db, uid)
    if old:
        from .cars import _remove_file
        _remove_file(old)
    return ok({"user": user})


# ---------------- Sessiyalar ----------------
@require()
async def sessions(request: Request):
    u = request.state.user
    with get_db() as db:
        items = rows(db.execute("SELECT id, ip, user_agent, created_at, last_seen FROM sessions WHERE user_id = ? AND revoked_at IS NULL "
                                "ORDER BY last_seen DESC LIMIT 20", (u["id"],)))
    for s in items:
        s["current"] = s["id"] == u["session_id"]
        s["id"] = s["id"][:16]     # to'liq xeshni tashqariga bermaymiz
    return ok({"items": items})


@require()
async def revoke_session(request: Request):
    u = request.state.user
    sid = request.path_params["sid"]
    with get_db() as db:
        db.execute("UPDATE sessions SET revoked_at = datetime('now') WHERE user_id = ? AND substr(id, 1, 16) = ? AND revoked_at IS NULL",
                   (u["id"], sid[:16]))
    return ok()


@require()
async def logout_all(request: Request):
    u = request.state.user
    with get_db() as db:
        revoke_user_sessions(db, u["id"], except_sid=u["session_id"])
        security_event(db, request, u, "sessions_revoked")
    return ok()


@require("user")
async def delete_account(request: Request):
    """Akkauntni o'chirish: parol bilan tasdiqlanadi; faol bronlar bo'lsa ruxsat berilmaydi.
    Shaxsiy ma'lumotlar anonimlashtiriladi, moliyaviy yozuvlar hisob uchun saqlanadi."""
    data = await parse_body(request, PasswordConfirmIn)
    u = request.state.user
    with get_db() as db:
        row = one(db.execute("SELECT password_hash FROM users WHERE id = ?", (u["id"],)))
        if not verify_password(data.password, row["password_hash"]):
            raise HTTPException(400, tr("Parol noto'g'ri"))
        active = db.execute(
            "SELECT COUNT(*) FROM bookings b JOIN cars c ON c.id = b.car_id WHERE b.status IN ('pending', 'approved') "
            "AND (b.renter_id = ? OR c.owner_id = ?)", (u["id"], u["id"])).fetchone()[0]
        if active:
            raise HTTPException(409, tr("Faol bronlaringiz bor. Avval ularni yakunlang yoki bekor qiling"))
        with transaction(db):
            db.execute("""UPDATE users SET full_name = ?, email = ?, phone = NULL, phone_norm = NULL, region = NULL, avatar = NULL,
                          password_hash = ?, is_active = 0, deleted_at = datetime('now'), marketing_ok = 0 WHERE id = ?""",
                       ("—", f"deleted-{u['id']}-{secrets.token_hex(4)}@deleted.local", hash_password(secrets.token_hex(16)), u["id"]))
            db.execute("UPDATE cars SET is_active = 0 WHERE owner_id = ?", (u["id"],))
            db.execute("DELETE FROM favorites WHERE user_id = ?", (u["id"],))
            revoke_user_sessions(db, u["id"])
            audit(db, request, "account_deleted", "user", u["id"])
    resp = ok()
    clear_auth_cookie(resp)
    return resp


@require()
async def summary(request: Request):
    uid = request.state.user["id"]
    with get_db() as db:
        n = db.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0", (uid,)).fetchone()[0]
        m = db.execute("SELECT COUNT(*) FROM messages WHERE receiver_id = ? AND is_read = 0", (uid,)).fetchone()[0]
        p = db.execute("SELECT COUNT(*) FROM bookings b JOIN cars c ON c.id = b.car_id WHERE c.owner_id = ? AND b.status = 'pending'",
                       (uid,)).fetchone()[0]
        r = (db.execute("SELECT COUNT(*) FROM reports WHERE status = 'new'").fetchone()[0]
             if request.state.user["role"] == "admin" else 0)
    return ok({"unread_notifications": n, "unread_messages": m, "pending_requests": p, "open_reports": r})


def _local_client(request: Request) -> bool:
    """Test qutisi faqat shu kompyuter yoki lokal tarmoq (Wi-Fi) qurilmalariga ochiq — internetdan emas."""
    import ipaddress
    try:
        ip = ipaddress.ip_address(client_ip(request))
    except ValueError:
        return request.client is None or request.client.host == "testclient"
    return ip.is_loopback or ip.is_private


async def dev_outbox(request: Request):
    """Test pochta qutisi (faqat dev/demo). Productionda bu manzil mavjud emas (404)."""
    if not settings.DEV_INBOX or not _local_client(request):
        raise HTTPException(404, tr("API manzili topilmadi"))
    with get_db() as db:
        items = rows(db.execute("SELECT * FROM dev_outbox ORDER BY id DESC LIMIT 30"))
    return ok({"items": items, "email_real": settings.email_enabled, "sms_real": settings.sms_enabled})


routes = [
    Route("/api/auth/register", register, methods=["POST"]),
    Route("/api/auth/login", login, methods=["POST"]),
    Route("/api/auth/logout", logout, methods=["POST"]),
    Route("/api/auth/me", me, methods=["GET"]),
    Route("/api/auth/me", update_me, methods=["PUT"]),
    Route("/api/auth/forgot", forgot, methods=["POST"]),
    Route("/api/auth/reset", reset_password, methods=["POST"]),
    Route("/api/auth/change-password", change_password, methods=["POST"]),
    Route("/api/me/verify/start", verify_start, methods=["POST"]),
    Route("/api/me/verify/confirm", verify_confirm, methods=["POST"]),
    Route("/api/me/email/start", email_change_start, methods=["POST"]),
    Route("/api/me/email/confirm", email_change_confirm, methods=["POST"]),
    Route("/api/me/prefs", update_prefs, methods=["PUT"]),
    Route("/api/me/avatar", avatar, methods=["POST"]),
    Route("/api/me/sessions", sessions, methods=["GET"]),
    Route("/api/me/sessions/{sid:str}", revoke_session, methods=["DELETE"]),
    Route("/api/me/logout-all", logout_all, methods=["POST"]),
    Route("/api/me/delete", delete_account, methods=["POST"]),
    Route("/api/me/mode", set_mode, methods=["PATCH"]),
    Route("/api/me/lang", set_lang, methods=["PATCH"]),
    Route("/api/me/summary", summary, methods=["GET"]),
    Route("/api/dev/outbox", dev_outbox, methods=["GET"]),
]
