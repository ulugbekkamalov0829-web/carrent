"""Email va SMS yuborish.

- SMTP sozlangan bo'lsa (SMTP_HOST), email haqiqatan yuboriladi (Python standart smtplib).
- Eskiz.uz sozlangan bo'lsa (ESKIZ_EMAIL/ESKIZ_PASSWORD), SMS haqiqatan yuboriladi.
- Hech biri sozlanmagan va dev/demo rejimda bo'lsa, xat "test pochta qutisi"ga yoziladi (/dev-inbox.html).
  Bu haqiqiy yuborish emas va interfeysda shunday deb aniq yoziladi. Productionda test qutisi o'chiq.
Kodlar va tokenlar hech qachon logga yozilmaydi.
"""
import json
import logging
import smtplib
import ssl
import threading
import time
import urllib.parse
import urllib.request
from email.message import EmailMessage

from .config import settings
from .db import get_db

log = logging.getLogger("carrent.channels")

# Xat shablonlari: (mavzu, matn) har tilda
TEMPLATES = {
    "reset": {
        "uz": ("CarRent: parolni tiklash kodi", "Parolni tiklash kodingiz: {code}\nKod {ttl} daqiqa amal qiladi. Agar siz so‘ramagan bo‘lsangiz, bu xatni e’tiborsiz qoldiring."),
        "ru": ("CarRent: код восстановления пароля", "Ваш код восстановления пароля: {code}\nКод действует {ttl} минут. Если вы не запрашивали его, проигнорируйте это письмо."),
        "en": ("CarRent: password reset code", "Your password reset code: {code}\nThe code is valid for {ttl} minutes. If you didn't request it, ignore this message."),
    },
    "verify_email": {
        "uz": ("CarRent: emailni tasdiqlash", "Email manzilingizni tasdiqlash kodi: {code}\nKod {ttl} daqiqa amal qiladi."),
        "ru": ("CarRent: подтверждение email", "Код подтверждения email: {code}\nКод действует {ttl} минут."),
        "en": ("CarRent: confirm your email", "Your email confirmation code: {code}\nThe code is valid for {ttl} minutes."),
    },
    "verify_phone": {
        "uz": ("", "CarRent tasdiqlash kodi: {code}. Kod {ttl} daqiqa amal qiladi."),
        "ru": ("", "Код подтверждения CarRent: {code}. Действует {ttl} минут."),
        "en": ("", "CarRent confirmation code: {code}. Valid for {ttl} minutes."),
    },
    "change_email": {
        "uz": ("CarRent: yangi emailni tasdiqlash", "Yangi email manzilni tasdiqlash kodi: {code}\nKod {ttl} daqiqa amal qiladi."),
        "ru": ("CarRent: подтверждение нового email", "Код подтверждения нового email: {code}\nКод действует {ttl} минут."),
        "en": ("CarRent: confirm your new email", "Your new email confirmation code: {code}\nThe code is valid for {ttl} minutes."),
    },
    "security": {
        "uz": ("CarRent: xavfsizlik bildirishnomasi", "Akkauntingizda muhim o‘zgarish: {what}.\nAgar buni siz qilmagan bo‘lsangiz, darhol parolni almashtiring va administratorga yozing."),
        "ru": ("CarRent: уведомление безопасности", "В вашем аккаунте важное изменение: {what}.\nЕсли это были не вы, срочно смените пароль и напишите администратору."),
        "en": ("CarRent: security notice", "An important change was made to your account: {what}.\nIf this wasn't you, change your password now and contact an administrator."),
    },
    "booking": {
        "uz": ("CarRent: {title}", "{title}\n{body}\n\n{url}"),
        "ru": ("CarRent: {title}", "{title}\n{body}\n\n{url}"),
        "en": ("CarRent: {title}", "{title}\n{body}\n\n{url}"),
    },
}


class DeliveryUnavailable(Exception):
    """Kanal sozlanmagan va test qutisi ham o'chiq (production)."""


def channel_available(channel: str) -> bool:
    if channel == "email":
        return settings.email_enabled or settings.DEV_INBOX
    return settings.sms_enabled or settings.DEV_INBOX


def render(template: str, lang: str, **params) -> tuple[str, str]:
    subj, body = TEMPLATES[template].get(lang) or TEMPLATES[template]["uz"]
    return subj.format(**params), body.format(**params)


def send(channel: str, to: str, template: str, lang: str = "uz", db=None, **params) -> str:
    """Xatni yuboradi. Qaytaradi: 'email' | 'sms' | 'dev_inbox'. Sozlanmagan bo'lsa DeliveryUnavailable.
    db berilsa, test qutisiga o'sha ulanish orqali yoziladi (ochiq tranzaksiya ichida bloklanmaslik uchun)."""
    subject, body = render(template, lang, **params)
    if channel == "email" and settings.email_enabled:
        threading.Thread(target=_smtp_send, args=(to, subject, body), daemon=True).start()
        return "email"
    if channel == "sms" and settings.sms_enabled:
        threading.Thread(target=_eskiz_send, args=(to, body), daemon=True).start()
        return "sms"
    if settings.DEV_INBOX:
        sql = "INSERT INTO dev_outbox (channel, to_addr, subject, body) VALUES (?, ?, ?, ?)"
        if db is not None:
            db.execute(sql, (channel, to, subject or None, body))
        else:
            with get_db() as conn:
                conn.execute(sql, (channel, to, subject or None, body))
        return "dev_inbox"
    raise DeliveryUnavailable(channel)


def _smtp_send(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.SMTP_FROM, to, subject
    msg.set_content(body)
    try:
        if settings.SMTP_PORT == 465:
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, context=ssl.create_default_context(), timeout=15) as s:
                if settings.SMTP_USER:
                    s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                s.send_message(msg)
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as s:
                s.starttls(context=ssl.create_default_context())
                if settings.SMTP_USER:
                    s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                s.send_message(msg)
    except Exception as exc:  # manzil va xato turini yozamiz, xat matnini (kodni) emas
        log.warning("Email yuborilmadi (%s): %s", to.split("@")[-1], type(exc).__name__)


_eskiz_token = {"value": None, "at": 0.0}


def _eskiz_post(path: str, data: dict, token: str | None = None) -> dict:
    req = urllib.request.Request("https://notify.eskiz.uz/api/" + path, data=urllib.parse.urlencode(data).encode(), method="POST")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode() or "{}")


def _eskiz_send(phone: str, text: str) -> None:
    try:
        if not _eskiz_token["value"] or time.time() - _eskiz_token["at"] > 20 * 86400:
            res = _eskiz_post("auth/login", {"email": settings.ESKIZ_EMAIL, "password": settings.ESKIZ_PASSWORD})
            _eskiz_token.update(value=res["data"]["token"], at=time.time())
        _eskiz_post("message/sms/send", {"mobile_phone": phone.lstrip("+"), "message": text, "from": settings.ESKIZ_FROM},
                    _eskiz_token["value"])
    except Exception as exc:
        log.warning("SMS yuborilmadi (...%s): %s", phone[-2:], type(exc).__name__)


def mask(target: str) -> str:
    """Foydalanuvchiga kod qayerga yuborilganini ko'rsatish: a***@gmail.com, +998 ** *** 45 67"""
    if "@" in target:
        name, dom = target.split("@", 1)
        return (name[:1] + "***@" + dom) if name else target
    return target[:4] + " ** *** " + target[-4:-2] + " " + target[-2:]


# ---------------- Bildirishnomalarni email/SMS orqali takrorlash ----------------
_LOCALES: dict[str, dict] = {}


def _locale(lang: str) -> dict:
    if lang not in _LOCALES:
        path = settings.STATIC_DIR / "locales" / f"{lang}.json"
        try:
            _LOCALES[lang] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _LOCALES[lang] = {}
    return _LOCALES[lang]


def render_notification(lang: str, type_: str, params: dict) -> tuple[str, str]:
    """Bildirishnoma matni frontend bilan bir xil tarjima faylidan olinadi."""
    loc, base = _locale(lang), _locale("uz")
    p = dict(params)
    if "total" in p:
        p["total"] = f"{int(p['total']):,}".replace(",", " ") + " " + (loc.get("currency") or "so'm")
    for k in ("start", "end"):
        if p.get(k) and len(str(p[k])) == 10:
            y, m, d = str(p[k]).split("-")
            p[k] = f"{d}.{m}.{y}"
    if "rating" in p:
        p["stars"] = "★" * int(p["rating"])

    def fmt(key: str) -> str:
        tpl = loc.get(key) or base.get(key) or ""
        for k, v in p.items():
            tpl = tpl.replace("{" + k + "}", str(v))
        return tpl
    return fmt(f"notif.{type_}.t"), fmt(f"notif.{type_}.b")


EXTERNAL = {"booking_new": "booking", "booking_approved": "booking", "booking_rejected": "booking", "booking_cancelled": "booking",
            "booking_expired": "booking", "payment_paid": "booking", "payment_refunded": "booking", "message": "messages"}


def mirror_notification(db, user_id: int, type_: str, params: dict, link: str) -> None:
    """Foydalanuvchi sozlamalarida yoqilgan bo'lsa, bildirishnomani email/SMS'ga ham yuboradi. Xato bo'lsa jim o'tadi."""
    kind = EXTERNAL.get(type_)
    if not kind:
        return
    row = db.execute("SELECT email, phone_norm, lang, notify_prefs, is_active FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row or not row["is_active"]:
        return
    prefs = json.loads(row["notify_prefs"] or "{}")
    title, body = render_notification(row["lang"] or "uz", type_, params)
    url = settings.PUBLIC_URL + (link or "/")
    try:
        if prefs.get("email_booking" if kind == "booking" else "email_messages", kind == "booking"):
            send("email", row["email"], "booking", row["lang"] or "uz", db=db, title=title, body=body, url=url)
        if kind == "booking" and prefs.get("sms_booking") and row["phone_norm"]:
            send("sms", row["phone_norm"], "booking", row["lang"] or "uz", db=db, title=title, body="", url="")
    except DeliveryUnavailable:
        pass
