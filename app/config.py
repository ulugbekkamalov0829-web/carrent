"""Ilova sozlamalari. Qiymatlar muhit o'zgaruvchilaridan (yoki .env fayldan) olinadi."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Kichik .env o'quvchi (qo'shimcha kutubxonasiz)."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in ("1", "true", "yes", "on")


class Settings:
    ENV: str = os.getenv("APP_ENV", "development")
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
    DB_PATH: Path = Path(os.getenv("DB_PATH", DATA_DIR / "app.db"))
    UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", DATA_DIR / "uploads"))
    # Hujjatlar va dalolatnoma rasmlari: ochiq /uploads emas, faqat ruxsatli foydalanuvchiga API orqali beriladi
    PRIVATE_DIR: Path = Path(os.getenv("PRIVATE_DIR", DATA_DIR / "private"))
    STATIC_DIR: Path = BASE_DIR / "static"

    # JWT
    JWT_ALGORITHM: str = "HS256"
    TOKEN_TTL_HOURS: int = int(os.getenv("TOKEN_TTL_HOURS", "168"))  # 7 kun
    COOKIE_NAME: str = "access_token"
    COOKIE_SECURE: bool = _bool("COOKIE_SECURE", ENV == "production")

    # Demo rejimi: kirish sahifasida demo hisoblarni ko'rsatadi (productionda o'chiring)
    DEMO_MODE: bool = _bool("DEMO_MODE", True)

    # Cheklovlar
    MAX_IMAGE_MB: int = 8            # brauzer suratni oldindan kichraytiradi; server baribir qayta kodlaydi
    MAX_IMAGES_PER_CAR: int = 10
    MAX_BOOKING_DAYS: int = 60
    LOGIN_ATTEMPTS: int = 8          # shuncha urinish...
    LOGIN_WINDOW_SEC: int = 300      # ...shuncha soniya ichida
    REGISTER_PER_HOUR: int = int(os.getenv("REGISTER_PER_HOUR", "10"))  # bir IP'dan soatiga
    MAX_JSON_BODY: int = 64 * 1024                  # JSON so'rov tanasi chegarasi (bayt)
    MAX_UPLOAD_BODY: int = 25 * 1024 * 1024         # rasm yuklash so'rovi chegarasi

    # Tasdiqlash kodlari (parolni tiklash, email/telefonni tasdiqlash)
    CODE_TTL_MIN: int = int(os.getenv("CODE_TTL_MIN", "3"))   # qisqa muddat: kod 3 daqiqa amal qiladi
    CODE_MAX_ATTEMPTS: int = 5
    CODE_RESEND_SEC: int = int(os.getenv("CODE_RESEND_SEC", "60"))
    CODES_PER_DAY: int = int(os.getenv("CODES_PER_DAY", "10"))

    # Sayt manzili (to'lovdan qaytish havolalari uchun)
    PUBLIC_URL: str = os.getenv("PUBLIC_URL", "http://localhost:8000").rstrip("/")

    # Email (SMTP) — berilmasa, xatlar test pochta qutisiga tushadi (faqat dev/demo)
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "CarRent <no-reply@carrent.uz>")

    # SMS (Eskiz.uz)
    ESKIZ_EMAIL: str = os.getenv("ESKIZ_EMAIL", "")
    ESKIZ_PASSWORD: str = os.getenv("ESKIZ_PASSWORD", "")
    ESKIZ_FROM: str = os.getenv("ESKIZ_FROM", "4546")

    # To'lovlar
    CLICK_SERVICE_ID: str = os.getenv("CLICK_SERVICE_ID", "")
    CLICK_MERCHANT_ID: str = os.getenv("CLICK_MERCHANT_ID", "")
    CLICK_SECRET_KEY: str = os.getenv("CLICK_SECRET_KEY", "")
    PAYME_MERCHANT_ID: str = os.getenv("PAYME_MERCHANT_ID", "")
    PAYME_KEY: str = os.getenv("PAYME_KEY", "")
    # Payme sinov muhiti: true bo'lsa to'lov sahifasi test.paycom.uz (haqiqiy pul yechilmaydi; kassa "test" kaliti bilan)
    PAYME_TEST: bool = _bool("PAYME_TEST", False)

    def __init__(self) -> None:
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
        self.SECRET_KEY = os.getenv("SECRET_KEY") or self._persistent_secret()
        prod = self.ENV == "production"
        # Test pochta qutisi va test to'lov — faqat dev/demo'da; productionda hech qachon yoqilmaydi
        self.DEV_INBOX: bool = not prod and _bool("DEV_INBOX", True)
        self.PAYMENT_TEST_MODE: bool = not prod and _bool("PAYMENT_TEST_MODE", True)

    @property
    def email_enabled(self) -> bool:
        return bool(self.SMTP_HOST)

    @property
    def sms_enabled(self) -> bool:
        return bool(self.ESKIZ_EMAIL and self.ESKIZ_PASSWORD)

    @property
    def click_enabled(self) -> bool:
        return bool(self.CLICK_SERVICE_ID and self.CLICK_MERCHANT_ID and self.CLICK_SECRET_KEY)

    @property
    def payme_enabled(self) -> bool:
        return bool(self.PAYME_MERCHANT_ID and self.PAYME_KEY)

    def _persistent_secret(self) -> str:
        """SECRET_KEY berilmasa, bir marta yaratib faylda saqlaymiz (qayta ishga tushganda sessiyalar yo'qolmaydi)."""
        if self.ENV == "production":
            raise RuntimeError("Production rejimida SECRET_KEY muhit o'zgaruvchisi majburiy")
        key_file = self.DATA_DIR / ".secret_key"
        if key_file.exists():
            return key_file.read_text().strip()
        key = secrets.token_urlsafe(48)
        key_file.write_text(key)
        return key


settings = Settings()
