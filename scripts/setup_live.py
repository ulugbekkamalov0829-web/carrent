"""CarRent'ni haqiqiy ishga tushirish ustasi.

Ishlatish (loyiha papkasida):   python -m scripts.setup_live
 1) Email (SMTP) — Gmail "App password" bilan. Login darhol tekshiriladi va sinov xati yuboriladi.
 2) SMS (Eskiz.uz) — login darhol tekshiriladi, xohlasangiz sinov SMS yuboriladi.
 3) Click va Payme kalitlari (bo'lsa).
 4) Demo rejim o'chiriladi: test pochta qutisi va test to'lov yopiladi, kirish sahifasida demo hisoblar chiqmaydi.
 5) Xohlasangiz demo e'lonlar va demo foydalanuvchilar o'chiriladi (oldin baza nusxasi olinadi) va
    haqiqiy administrator yaratiladi.
Hamma qiymatlar .env faylga yoziladi (u .gitignore'da — GitHub'ga chiqmaydi). Eski .env nusxasi .env.bak ga saqlanadi.
"""
import getpass
import json
import secrets
import shutil
import smtplib
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"


def read_env() -> dict:
    out = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def write_env(values: dict) -> None:
    if ENV.exists():
        shutil.copyfile(ENV, ENV.with_suffix(".bak"))
    groups = [
        ("Umumiy", ["APP_ENV", "SECRET_KEY", "PUBLIC_URL", "DEMO_MODE", "DEV_INBOX", "PAYMENT_TEST_MODE", "COOKIE_SECURE", "CODE_TTL_MIN"]),
        ("Email (SMTP)", ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"]),
        ("SMS (Eskiz.uz)", ["ESKIZ_EMAIL", "ESKIZ_PASSWORD", "ESKIZ_FROM"]),
        ("Click", ["CLICK_SERVICE_ID", "CLICK_MERCHANT_ID", "CLICK_SECRET_KEY"]),
        ("Payme", ["PAYME_MERCHANT_ID", "PAYME_KEY", "PAYME_TEST"]),
    ]
    lines = [f"# CarRent sozlamalari — {datetime.now():%Y-%m-%d %H:%M} da setup_live yozdi. Bu faylni hech kimga bermang."]
    used = set()
    for title, keys in groups:
        lines.append(f"\n# ---- {title} ----")
        for k in keys:
            if k in values:
                lines.append(f"{k}={values[k]}"); used.add(k)
    rest = [k for k in values if k not in used]
    if rest:
        lines.append("\n# ---- Boshqa ----")
        lines += [f"{k}={values[k]}" for k in rest]
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ask(prompt: str, default: str = "", secret: bool = False) -> str:
    shown = " [saqlangan]" if secret and default else (f" [{default}]" if default else "")
    val = (getpass.getpass if secret else input)(f"  {prompt}{shown}: ").strip()
    return val or default


def yes(prompt: str, default: bool = True) -> bool:
    # H = ha, Y = yo'q (katta harf — Enter bosilganda tanlanadigani)
    v = input(f"  {prompt} [{'H/y' if default else 'h/Y'}]: ").strip().lower().replace("'", "").replace("ʻ", "")
    if not v:
        return default
    return v in ("h", "ha", "yes")


def ok(msg): print(f"  ✓ {msg}")
def bad(msg): print(f"  ✗ {msg}")


def test_smtp(env: dict, to: str | None) -> bool:
    host, port = env["SMTP_HOST"], int(env.get("SMTP_PORT") or 587)
    try:
        ctx = ssl.create_default_context()
        s = smtplib.SMTP_SSL(host, port, context=ctx, timeout=20) if port == 465 else smtplib.SMTP(host, port, timeout=20)
        with s:
            if port != 465:
                s.starttls(context=ctx)
            s.login(env["SMTP_USER"], env["SMTP_PASSWORD"])
            ok("SMTP login muvaffaqiyatli")
            if to:
                m = EmailMessage()
                m["From"], m["To"], m["Subject"] = env["SMTP_FROM"], to, "CarRent: sinov xati"
                m.set_content("Email yuborish ishlayapti. Endi tasdiqlash kodlari va bildirishnomalar shu manzildan boradi.")
                s.send_message(m)
                ok(f"Sinov xati yuborildi: {to} (Spam papkasini ham tekshiring)")
        return True
    except smtplib.SMTPAuthenticationError:
        bad("Login yoki parol noto'g'ri. Gmail uchun oddiy parol emas, 16 belgili 'App password' kerak.")
    except Exception as e:
        bad(f"Ulanib bo'lmadi: {type(e).__name__}: {e}")
    return False


def eskiz(path: str, data: dict, token: str | None = None) -> dict:
    req = urllib.request.Request("https://notify.eskiz.uz/api/" + path, data=urllib.parse.urlencode(data).encode(), method="POST")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode() or "{}")
        except ValueError:
            body = {}
        raise RuntimeError(f"HTTP {e.code}: {body.get('message') or body}") from None


def test_eskiz(env: dict, phone: str | None) -> bool:
    try:
        tok = eskiz("auth/login", {"email": env["ESKIZ_EMAIL"], "password": env["ESKIZ_PASSWORD"]})["data"]["token"]
        ok("Eskiz login muvaffaqiyatli")
    except Exception as e:
        bad(f"Eskiz login xato: {e}")
        return False
    if phone:
        digits = "".join(c for c in phone if c.isdigit())
        if len(digits) == 9:
            digits = "998" + digits
        try:
            # Shablon moderatsiyadan o'tmaguncha Eskiz faqat o'z test matnini yuboradi
            text = "CarRent: sinov xabari. SMS yuborish ishlayapti."
            res = eskiz("message/sms/send", {"mobile_phone": digits, "message": text, "from": env.get("ESKIZ_FROM") or "4546"}, tok)
            ok(f"SMS yuborildi (id={res.get('id')}). Telefoningizni tekshiring.")
        except Exception as e:
            bad(f"SMS yuborilmadi: {e}")
            print("    Ehtimol shablon hali tasdiqlanmagan. Eskiz kabinetida 'Shablonlar' bo'limiga matnlarni yuboring\n"
                  "    (admin panel -> SMS va email -> SMS shablonlari). Tasdiqlangach qayta urinib ko'ring.")
    return True


def remove_demo() -> None:
    sys.path.insert(0, str(ROOT))
    from app.config import settings
    from app.db import get_db, init_db
    init_db()
    backup = Path(str(settings.DB_PATH) + f".demo-backup-{datetime.now():%Y%m%d-%H%M}")
    shutil.copyfile(settings.DB_PATH, backup)
    ok(f"Baza nusxasi: {backup.name}")
    with get_db() as db:
        n_cars = db.execute("DELETE FROM cars WHERE is_demo = 1").rowcount
        n_users = db.execute("DELETE FROM users WHERE email LIKE '%@carrent.uz'").rowcount
        db.execute("DELETE FROM dev_outbox")
    ok(f"O'chirildi: {n_cars} ta demo e'lon, {n_users} ta demo foydalanuvchi")


def create_admin() -> None:
    sys.path.insert(0, str(ROOT))
    from app.db import get_db, init_db
    from app.schemas import _check_password
    from app.security import hash_password
    init_db()
    email = ask("Administrator email").lower()
    name = ask("Ism familiya", "Administrator")
    while True:
        pw = getpass.getpass("  Parol: ")
        try:
            _check_password(pw)
        except ValueError as e:
            bad(str(e)); continue
        if pw != getpass.getpass("  Parolni takrorlang: "):
            bad("Parollar mos emas"); continue
        break
    with get_db() as db:
        if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            db.execute("UPDATE users SET role = 'admin', is_active = 1, password_hash = ?, full_name = ? WHERE email = ?",
                       (hash_password(pw), name, email))
        else:
            db.execute("INSERT INTO users (full_name, email, phone, password_hash, role, email_verified) VALUES (?, ?, '', ?, 'admin', 1)",
                       (name, email, hash_password(pw)))
    ok(f"Administrator tayyor: {email}")


def main() -> None:
    env = read_env()
    print("\n=== CarRent: haqiqiy ishga tushirish ===\nEnter — qavs ichidagi qiymatni qoldiradi.\n")
    env.setdefault("SECRET_KEY", secrets.token_urlsafe(48))
    env["PUBLIC_URL"] = ask("Sayt manzili (internetga joylasangiz https://... , hozircha kompyuterda)", env.get("PUBLIC_URL", "http://localhost:8000"))

    print("\n1) EMAIL (tasdiqlash kodlari va bildirishnomalar)")
    print("   Gmail: myaccount.google.com -> Xavfsizlik -> 2 bosqichli tasdiqlash ON -> 'App passwords' -> 16 belgili parol")
    if yes("Email sozlansinmi?"):
        env["SMTP_HOST"] = ask("SMTP server", env.get("SMTP_HOST", "smtp.gmail.com"))
        env["SMTP_PORT"] = ask("Port", env.get("SMTP_PORT", "587"))
        env["SMTP_USER"] = ask("Email manzil (login)", env.get("SMTP_USER", ""))
        env["SMTP_PASSWORD"] = ask("App password", env.get("SMTP_PASSWORD", ""), secret=True).replace(" ", "")
        env["SMTP_FROM"] = f"CarRent <{env['SMTP_USER']}>"
        test_smtp(env, ask("Sinov xati qaysi manzilga? (bo'sh — yubormaslik)") or None)

    print("\n2) SMS (Eskiz.uz) — my.eskiz.uz da ro'yxatdan o'ting va balansni to'ldiring")
    if yes("SMS sozlansinmi?", bool(env.get("ESKIZ_EMAIL"))):
        env["ESKIZ_EMAIL"] = ask("Eskiz login (email)", env.get("ESKIZ_EMAIL", ""))
        env["ESKIZ_PASSWORD"] = ask("Eskiz parol / API kalit", env.get("ESKIZ_PASSWORD", ""), secret=True)
        env["ESKIZ_FROM"] = ask("Jo'natuvchi nomi (tasdiqlangan bo'lsa)", env.get("ESKIZ_FROM", "4546"))
        test_eskiz(env, ask("Sinov SMS qaysi raqamga? (bo'sh — yubormaslik)") or None)

    print("\n3) TO'LOVLAR (Click/Payme bilan shartnoma tuzilgandan keyin beriladigan kalitlar)")
    if yes("Click kalitlari bormi?", bool(env.get("CLICK_SERVICE_ID"))):
        for k, label in (("CLICK_SERVICE_ID", "Service ID"), ("CLICK_MERCHANT_ID", "Merchant ID")):
            env[k] = ask(label, env.get(k, ""))
        env["CLICK_SECRET_KEY"] = ask("Secret key", env.get("CLICK_SECRET_KEY", ""), secret=True)
        print(f"   Click kabinetida Prepare va Complete URL: {env['PUBLIC_URL']}/api/payments/click")
    if yes("Payme kalitlari bormi?", bool(env.get("PAYME_MERCHANT_ID"))):
        env["PAYME_MERCHANT_ID"] = ask("Kassa ID (merchant)", env.get("PAYME_MERCHANT_ID", ""))
        env["PAYME_KEY"] = ask("Kassa kaliti (test yoki asosiy)", env.get("PAYME_KEY", ""), secret=True)
        env["PAYME_TEST"] = "true" if yes("Bu TEST kalitmi? (sinov uchun test.paycom.uz)", env.get("PAYME_TEST") == "true") else "false"
        print(f"   Payme kabinetida Endpoint URL: {env['PUBLIC_URL']}/api/payments/payme")

    print("\n4) DEMO REJIMNI O'CHIRISH")
    if yes("Demo o'chirilsinmi? (test pochta qutisi, test to'lov va demo hisoblar tugmalari yopiladi)"):
        env.update(DEMO_MODE="false", DEV_INBOX="false", PAYMENT_TEST_MODE="false")
        if not env.get("SMTP_HOST") and not env.get("ESKIZ_EMAIL"):
            bad("Diqqat: email ham, SMS ham sozlanmagan — kodlar hech qayerga bormaydi (parolni tiklash ishlamaydi).")
    write_env(env)
    ok(f".env saqlandi ({ENV})")

    if yes("Demo e'lonlar va demo foydalanuvchilar o'chirilsinmi? (baza nusxasi olinadi)", False):
        remove_demo()
        print("   Endi haqiqiy administratorni yarating:")
        create_admin()
    elif yes("Yangi administrator yaratilsinmi?", False):
        create_admin()

    print("\nTayyor. Serverni qayta ishga tushiring (run.bat). Admin panel -> 'SMS va email' bo'limida holatni ko'rasiz.\n")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nTo'xtatildi. .env o'zgarmadi.")
