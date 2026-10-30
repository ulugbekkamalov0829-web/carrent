"""Kiruvchi ma'lumotlarni tekshirish (Pydantic). Xato matnlari i18n orqali uch tilda qaytadi."""
import re
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .security import COMMON_PASSWORDS, normalize_phone

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^\+?[0-9 ()-]{7,20}$")

Transmission = Literal["automatic", "manual"]
Fuel = Literal["petrol", "gas", "diesel", "hybrid", "electric"]
BodyType = Literal["sedan", "hatchback", "crossover", "suv", "minivan", "pickup", "coupe"]
Drive = Literal["fwd", "rwd", "awd"]
FEATURES = {"ac", "bluetooth", "usb", "camera", "parking_sensors", "cruise", "heated_seats", "child_seat",
            "navigation", "sunroof", "leather", "abs", "airbags", "carplay"}
PASSWORD_MIN = 12


class Base(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


def _check_phone(v: str) -> str:
    norm = normalize_phone(v) if PHONE_RE.match(v or "") else None
    if not norm:
        raise ValueError("Telefon raqam noto'g'ri")
    return norm


def _check_password(v: str) -> str:
    # Uzun parol va passphrase qo'llab-quvvatlanadi; majburiy belgi turlari yo'q (NIST 800-63B tavsiyasi)
    if v.lower() in COMMON_PASSWORDS or len(set(v)) <= 3:
        raise ValueError("Parol juda keng tarqalgan — boshqasini tanlang")
    return v


class RegisterIn(Base):
    full_name: str = Field(min_length=3, max_length=80)
    email: str = Field(max_length=120)
    phone: str = Field(max_length=20)
    password: str = Field(min_length=PASSWORD_MIN, max_length=128)
    accept_terms: bool
    marketing_ok: bool = False
    lang: Literal["uz", "ru", "en"] = "uz"

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        if not EMAIL_RE.match(v):
            raise ValueError("Email manzil noto'g'ri")
        return v.lower()

    _phone = field_validator("phone")(classmethod(lambda cls, v: _check_phone(v)))
    _pw = field_validator("password")(classmethod(lambda cls, v: _check_password(v)))

    @model_validator(mode="after")
    def _cross(self):
        if not self.accept_terms:
            raise ValueError("Foydalanish shartlariga rozilik majburiy")
        if self.email.split("@")[0] and self.email.split("@")[0] in self.password.lower():
            raise ValueError("Parol email manzilingizni o'z ichiga olmasligi kerak")
        return self


class LoginIn(Base):
    # email yoki telefon raqami (eski mijozlar uchun "email" maydoni ham qabul qilinadi)
    login: Optional[str] = Field(default=None, max_length=120)
    email: Optional[str] = Field(default=None, max_length=120)
    password: str = Field(max_length=128)

    @property
    def identifier(self) -> str:
        return (self.login or self.email or "").strip()


class ForgotIn(Base):
    login: str = Field(min_length=3, max_length=120)


class ResetIn(Base):
    login: str = Field(min_length=3, max_length=120)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(min_length=PASSWORD_MIN, max_length=128)
    _pw = field_validator("new_password")(classmethod(lambda cls, v: _check_password(v)))


class VerifyStartIn(Base):
    channel: Literal["email", "sms"]


class VerifyConfirmIn(Base):
    channel: Literal["email", "sms"]
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class EmailChangeIn(Base):
    new_email: str = Field(max_length=120)
    password: str = Field(max_length=128)

    @field_validator("new_email")
    @classmethod
    def _email(cls, v: str) -> str:
        if not EMAIL_RE.match(v):
            raise ValueError("Email manzil noto'g'ri")
        return v.lower()


class CodeIn(Base):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class PasswordConfirmIn(Base):
    password: str = Field(max_length=128)


class PrefsIn(Base):
    show_phone: bool = True
    marketing_ok: bool = False
    email_booking: bool = True
    email_messages: bool = False
    sms_booking: bool = False


class ProfileIn(Base):
    full_name: str = Field(min_length=3, max_length=80)
    phone: str = Field(max_length=20)
    region: Optional[str] = Field(default=None, max_length=40)
    _phone = field_validator("phone")(classmethod(lambda cls, v: _check_phone(v)))


class PasswordChangeIn(Base):
    old_password: str = Field(max_length=128)
    new_password: str = Field(min_length=PASSWORD_MIN, max_length=128)
    _pw = field_validator("new_password")(classmethod(lambda cls, v: _check_password(v)))


class ModeIn(Base):
    mode: Literal["renter", "owner"]


class LangIn(Base):
    lang: Literal["uz", "ru", "en"]


class CarIn(Base):
    brand: str = Field(min_length=2, max_length=40)
    model: str = Field(min_length=1, max_length=40)
    year: int = Field(ge=1990, le=date.today().year + 1)
    color: Optional[str] = Field(default=None, max_length=30)
    body_type: BodyType
    seats: int = Field(ge=1, le=20)
    transmission: Transmission
    fuel: Fuel
    engine_l: Optional[float] = Field(default=None, ge=0.6, le=8.0)
    mileage_km: Optional[int] = Field(default=None, ge=0, le=2_000_000)
    drive: Optional[Drive] = None
    features: list[str] = Field(default_factory=list, max_length=20)
    city: str = Field(min_length=2, max_length=40)
    description: Optional[str] = Field(default=None, max_length=2000)
    price_per_day: int = Field(ge=10_000, le=50_000_000)
    deposit: int = Field(default=0, ge=0, le=100_000_000)
    min_days: int = Field(default=1, ge=1, le=60)
    max_days: int = Field(default=30, ge=1, le=90)
    km_limit: Optional[int] = Field(default=None, ge=50, le=2000)
    delivery_price: Optional[int] = Field(default=None, ge=0, le=5_000_000)
    is_active: bool = True

    @field_validator("features")
    @classmethod
    def _features(cls, v: list[str]) -> list[str]:
        for key in v:
            if key not in FEATURES:
                raise ValueError("Ruxsat etilgan qiymatlardan birini tanlang")
        return sorted(set(v))

    @model_validator(mode="after")
    def _days(self):
        if self.max_days < self.min_days:
            raise ValueError("Maksimal muddat minimaldan kam bo'lmasligi kerak")
        return self


class BookingIn(Base):
    car_id: int
    start_date: date
    end_date: date
    delivery: bool = False
    note: Optional[str] = Field(default=None, max_length=500)


class ReviewIn(Base):
    booking_id: int
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = Field(default=None, max_length=1000)


class ReplyIn(Base):
    reply: str = Field(min_length=1, max_length=1000)


class MessageIn(Base):
    to_user_id: int
    body: str = Field(min_length=1, max_length=2000)
    car_id: Optional[int] = None


class PaymentIn(Base):
    booking_id: int
    provider: Literal["test", "click", "payme"]


class BlockIn(Base):
    start_date: date
    end_date: date
    note: Optional[str] = Field(default=None, max_length=200)


class ReportIn(Base):
    target_type: Literal["car", "review", "user", "message"]
    target_id: int
    reason: Literal["fake", "fraud", "abuse", "wrong_info", "spam", "other"]
    comment: Optional[str] = Field(default=None, max_length=1000)


class ReportPatch(Base):
    status: Literal["resolved", "dismissed"]
    action: Optional[Literal["hide_car", "delete_review", "block_user"]] = None


class ImageOrderIn(Base):
    ids: list[int] = Field(min_length=1, max_length=20)


class ImageLabelIn(Base):
    label: Literal["front", "back", "side", "interior", "dashboard", "trunk", "other"]


class PayoutIn(Base):
    owner_id: int
    amount: int = Field(gt=0, le=10_000_000_000)
    note: Optional[str] = Field(default=None, max_length=200)


class AdminUserPatch(Base):
    is_active: bool


class AdminCarPatch(Base):
    is_approved: bool


class SettingsIn(Base):
    commission_percent: float = Field(ge=0, le=30)
