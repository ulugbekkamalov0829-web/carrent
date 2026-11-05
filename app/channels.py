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
import urllib.error
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
    "pin_reset": {
        "uz": ("CarRent: ilova PIN kodini tiklash", "Ilova PIN kodini tiklash kodingiz: {code}\nKod {ttl} daqiqa amal qiladi. Agar siz so‘ramagan bo‘lsangiz, parolingizni almashtiring."),
        "ru": ("CarRent: сброс PIN-кода приложения", "Код для сброса PIN-кода приложения: {code}\nКод действует {ttl} минут. Если это были не вы — смените пароль."),
        "en": ("CarRent: reset your app PIN", "Your app PIN reset code: {code}\nThe code is valid for {ttl} minutes. If this wasn't you, change your password."),
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
    "sign_contract": {
        "uz": ("CarRent: shartnomani imzolash kodi", "Ijara shartnomasi {number} ni imzolash kodi: {code}\nKod {ttl} daqiqa amal qiladi. Kodni kiritish orqali shartnoma shartlariga roziligingizni bildirasiz. Kodni hech kimga bermang."),
        "ru": ("CarRent: код подписания договора", "Код подписания договора аренды {number}: {code}\nКод действует {ttl} минут. Вводя код, вы соглашаетесь с условиями договора. Никому не сообщайте код."),
        "en": ("CarRent: contract signing code", "Code to sign rental contract {number}: {code}\nValid for {ttl} minutes. By entering it you accept the contract terms. Never share this code."),
    },
    "booking": {
        "uz": ("CarRent: {title}", "{title}\n{body}\n\n{url}"),
        "ru": ("CarRent: {title}", "{title}\n{body}\n\n{url}"),
        "en": ("CarRent: {title}", "{title}\n{body}\n\n{url}"),
    },
}


# SMS uchun qisqa, o'zgarmas matnlar. Eskiz faqat moderatsiyadan o'tgan shablonlarni yuboradi — shu matnlarni
# Eskiz kabinetida "Shablonlar" bo'limiga AYNAN shunday yuborish kerak ({code}, {ttl}, {title} o'rniga qiymat qo'yiladi).
SMS_TEMPLATES = {
    "reset": {"uz": "CarRent: parolni tiklash kodi {code}. Kod {ttl} daqiqa amal qiladi. Kodni hech kimga bermang.",
              "ru": "CarRent: код восстановления пароля {code}. Действует {ttl} минут. Никому не сообщайте код.",
              "en": "CarRent: password reset code {code}. Valid for {ttl} minutes. Never share this code."},
    "verify_phone": {"uz": "CarRent: telefon raqamni tasdiqlash kodi {code}. Kod {ttl} daqiqa amal qiladi.",
                     "ru": "CarRent: код подтверждения телефона {code}. Действует {ttl} минут.",
                     "en": "CarRent: phone confirmation code {code}. Valid for {ttl} minutes."},
    "pin_reset": {"uz": "CarRent: ilova PIN kodini tiklash kodi {code}. Kod {ttl} daqiqa amal qiladi. Kodni hech kimga bermang.",
                  "ru": "CarRent: код сброса PIN-кода {code}. Действует {ttl} минут. Никому не сообщайте код.",
                  "en": "CarRent: app PIN reset code {code}. Valid for {ttl} minutes. Never share this code."},
    "booking": {"uz": "CarRent: {title}", "ru": "CarRent: {title}", "en": "CarRent: {title}"},
    "test": {"uz": "CarRent: sinov xabari. SMS yuborish ishlayapti.", "ru": "CarRent: тестовое сообщение. Отправка SMS работает.",
             "en": "CarRent: test message. SMS delivery works."},
}
TEMPLATES["test"] = {"uz": ("CarRent: sinov xati", "Bu sinov xati. Email yuborish ishlayapti."),
                     "ru": ("CarRent: тестовое письмо", "Это тестовое письмо. Отправка email работает."),
                     "en": ("CarRent: test email", "This is a test email. Email delivery works.")}


class DeliveryUnavailable(Exception):
    """Kanal sozlanmagan va test qutisi ham o'chiq (production)."""


def channel_available(channel: str) -> bool:
    if channel == "email":
        return settings.email_enabled or settings.DEV_INBOX
    return settings.sms_enabled or settings.DEV_INBOX


def render(template: str, lang: str, channel: str = "email", **params) -> tuple[str, str]:
    if channel == "sms" and template in SMS_TEMPLATES:
        body = SMS_TEMPLATES[template].get(lang) or SMS_TEMPLATES[template]["uz"]
        return "", body.format(**params)
    subj, body = TEMPLATES[template].get(lang) or TEMPLATES[template]["uz"]
    return subj.format(**params), body.format(**params)


def _log(db, channel: str, to: str, template: str, status: str, error: str | None = None, provider_id: str | None = None) -> int:
    """Yuborish jurnali (admin panel uchun). Xat matni va kod YOZILMAYDI — faqat kimga (yashirilgan), qaysi shablon, natija."""
    sql = "INSERT INTO message_log (channel, to_masked, template, status, error, provider_id) VALUES (?, ?, ?, ?, ?, ?)"
    args = (channel, mask(to), template, status, (error or "")[:200] or None, provider_id)
    if db is not None:
        return db.execute(sql, args).lastrowid
    with get_db() as conn:
        return conn.execute(sql, args).lastrowid


def _update_log(log_id: int, status: str, error: str | None = None, provider_id: str | None = None) -> None:
    try:
        with get_db() as conn:
            conn.execute("UPDATE message_log SET status = ?, error = COALESCE(?, error), provider_id = COALESCE(?, provider_id), "
                         "updated_at = datetime('now') WHERE id = ?", (status, (error or "")[:200] or None, provider_id, log_id))
    except Exception:   # jurnal yozilmasa ham asosiy ish to'xtamaydi
        pass


def send(channel: str, to: str, template: str, lang: str = "uz", db=None, **params) -> str:
    """Xatni yuboradi. Qaytaradi: 'email' | 'sms' | 'dev_inbox'. Sozlanmagan bo'lsa DeliveryUnavailable.
    db berilsa, test qutisiga o'sha ulanish orqali yoziladi (ochiq tranzaksiya ichida bloklanmaslik uchun)."""
    subject, body = render(template, lang, channel, **params)
    if channel == "email" and settings.email_enabled:
        log_id = _log(db, "email", to, template, "queued")
        threading.Thread(target=_email_send, args=(to, subject, body, log_id), daemon=True).start()
        return "email"
    if channel == "sms" and settings.sms_enabled:
        log_id = _log(db, "sms", to, template, "queued")
        threading.Thread(target=_eskiz_send, args=(to, body, log_id), daemon=True).start()
        return "sms"
    if settings.DEV_INBOX:
        sql = "INSERT INTO dev_outbox (channel, to_addr, subject, body) VALUES (?, ?, ?, ?)"
        if db is not None:
            db.execute(sql, (channel, to, subject or None, body))
        else:
            with get_db() as conn:
                conn.execute(sql, (channel, to, subject or None, body))
        _log(db, channel, to, template, "dev")
        return "dev_inbox"
    raise DeliveryUnavailable(channel)


def send_now(channel: str, to: str, template: str = "test", lang: str = "uz") -> dict:
    """Admin sinovi: kutib turib yuboradi va provayderning haqiqiy javobini qaytaradi (xato matni bilan)."""
    subject, body = render(template, lang, channel)
    if channel == "email" and settings.email_enabled:
        log_id = _log(None, "email", to, template, "queued")
        return _email_send(to, subject, body, log_id)
    if channel == "sms" and settings.sms_enabled:
        log_id = _log(None, "sms", to, template, "queued")
        return _eskiz_send(to, body, log_id)
    return {"status": send(channel, to, template, lang)}


def _email_send(to: str, subject: str, body: str, log_id: int | None = None) -> dict:
    return (_relay_send if settings.EMAIL_RELAY_URL else _smtp_send)(to, subject, body, log_id)


def _relay_send(to: str, subject: str, body: str, log_id: int | None = None) -> dict:
    """Gmail ko'prigi (Google Apps Script veb-ilovasi) orqali HTTPS bilan yuborish.
    Ko'prik {"ok": true} qaytaradi; token mos kelmasa yoki Gmail rad etsa — {"ok": false, "error": "..."}."""
    payload = json.dumps({"token": settings.EMAIL_RELAY_TOKEN, "to": to, "subject": subject, "body": body,
                          "name": settings.SMTP_FROM.split("<")[0].strip() or "CarRent"}).encode()
    req = urllib.request.Request(settings.EMAIL_RELAY_URL, data=payload, method="POST",
                                 headers={"Content-Type": "text/plain;charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:   # Apps Script 302 bilan javob sahifasiga yo'naltiradi — urllib o'zi ergashadi
            raw = r.read().decode("utf-8", "replace")
        try:
            res = json.loads(raw)
        except ValueError:
            res = {"ok": False, "error": "Ko'prik JSON qaytarmadi (Apps Script 'Anyone' uchun ochiq deploy qilinganini tekshiring): " + raw[:80]}
        if not res.get("ok"):
            raise RuntimeError(str(res.get("error") or "relay error"))
    except Exception as exc:
        log.warning("Email (ko'prik) yuborilmadi (%s): %s", to.split("@")[-1], type(exc).__name__)
        err = f"{type(exc).__name__}: {exc}"[:200]
        if log_id:
            _update_log(log_id, "failed", err)
        return {"status": "failed", "error": err}
    if log_id:
        _update_log(log_id, "sent")
    return {"status": "sent"}


def _smtp_send(to: str, subject: str, body: str, log_id: int | None = None) -> dict:
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
        err = f"{type(exc).__name__}: {exc}"[:200]
        if log_id:
            _update_log(log_id, "failed", err)
        return {"status": "failed", "error": err}
    if log_id:
        _update_log(log_id, "sent")
    return {"status": "sent"}


_eskiz_token = {"value": None, "at": 0.0}


ESKIZ_API = "https://notify.eskiz.uz/api/"
_eskiz_lock = threading.Lock()


def _eskiz_post(path: str, data: dict, token: str | None = None) -> dict:
    req = urllib.request.Request(ESKIZ_API + path, data=urllib.parse.urlencode(data).encode(), method="POST")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:   # Eskiz xato sababini JSON'da qaytaradi (masalan, shablon tasdiqlanmagan)
        try:
            detail = json.loads(e.read().decode() or "{}")
        except ValueError:
            detail = {}
        raise EskizError(e.code, detail.get("message") or detail.get("status") or str(e)) from None


class EskizError(Exception):
    def __init__(self, code: int, msg):
        super().__init__(f"HTTP {code}: {msg}")
        self.code = code


def _eskiz_token_get(force: bool = False) -> str:
    """Token 30 kun amal qiladi; 20 kunda yoki 401 javobida qayta olinadi."""
    with _eskiz_lock:
        if force or not _eskiz_token["value"] or time.time() - _eskiz_token["at"] > 20 * 86400:
            res = _eskiz_post("auth/login", {"email": settings.ESKIZ_EMAIL, "password": settings.ESKIZ_PASSWORD})
            _eskiz_token.update(value=res["data"]["token"], at=time.time())
        return _eskiz_token["value"]


def _eskiz_send(phone: str, text: str, log_id: int | None = None) -> dict:
    data = {"mobile_phone": "".join(ch for ch in phone if ch.isdigit()), "message": text, "from": settings.ESKIZ_FROM}
    if log_id and settings.PUBLIC_URL.startswith("https://"):
        data["callback_url"] = f"{settings.PUBLIC_URL}/api/channels/eskiz/callback?log={log_id}&sig={callback_sig(log_id)}"
    try:
        try:
            res = _eskiz_post("message/sms/send", data, _eskiz_token_get())
        except EskizError as e:
            if e.code != 401:
                raise
            res = _eskiz_post("message/sms/send", data, _eskiz_token_get(force=True))   # token eskirgan — bir marta qayta
        pid = str(res.get("id") or "") or None
        if log_id:
            _update_log(log_id, "sent", provider_id=pid)
        return {"status": "sent", "provider_id": pid}
    except Exception as exc:
        log.warning("SMS yuborilmadi (...%s): %s", phone[-2:], type(exc).__name__)
        err = str(exc)[:200]
        if log_id:
            _update_log(log_id, "failed", err)
        return {"status": "failed", "error": err}


def callback_sig(log_id: int) -> str:
    import hashlib
    import hmac
    return hmac.new(settings.SECRET_KEY.encode(), f"eskiz:{log_id}".encode(), hashlib.sha256).hexdigest()[:24]


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
