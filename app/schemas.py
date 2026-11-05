"""Kiruvchi ma'lumotlarni tekshirish (Pydantic). Xato matnlari i18n orqali uch tilda qaytadi."""
import re
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .regions import normalize_region, valid_district
from .security import COMMON_PASSWORDS, normalize_phone

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^\+?[0-9 ()-]{7,20}$")

Transmission = Literal["automatic", "manual"]
Fuel = Literal["petrol", "gas", "diesel", "hybrid", "electric"]
BodyType = Literal["sedan", "hatchback", "crossover", "suv", "minivan", "pickup", "coupe"]
Drive = Literal["fwd", "rwd", "awd"]
FEATURES = {"ac", "bluetooth", "usb", "camera", "parking_sensors", "cruise", "heated_seats", "child_seat",
            "navigation", "sunroof", "leather", "abs", "airbags", "carplay",
            # v4: yangi qulayliklar
            "climate", "camera360", "dashcam", "isofix", "keyless", "ventilated_seats", "roof_rack", "winter_tires",
            "wifi", "phone_charger", "pets_ok", "lane_assist"}
PASSWORD_MIN = 8


class Base(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


def _check_place(region: str | None, district: str | None, required: bool) -> tuple[str | None, str | None]:
    """Hudud ro'yxatdagilardan biri, tuman esa aynan shu hududga tegishli bo'lishi kerak."""
    if not region:
        if required:
            raise ValueError("Viloyatni tanlang")
        return None, None
    canon = normalize_region(region)
    if not canon:
        raise ValueError("Viloyat ro'yxatda yo'q")
    district = (district or "").strip() or None
    if required and not district:
        raise ValueError("Tuman yoki shaharni tanlang")
    if not valid_district(canon, district):
        raise ValueError("Bu tuman tanlangan viloyatga tegishli emas")
    return canon, district


def _check_phone(v: str) -> str:
    norm = normalize_phone(v) if PHONE_RE.match(v or "") else None
    if not norm:
        raise ValueError("Telefon raqam noto'g'ri")
    return norm


# Parol qoidalari — sahifadagi ro'yxat (static/js/app.js: PW_RULES) bilan bir xil
PW_RULES = (
    ("len", lambda v: len(v) >= PASSWORD_MIN, "Parol kamida {n} ta belgidan iborat bo'lsin"),
    ("upper", lambda v: any(c.isupper() for c in v), "Kamida bitta katta harf (A–Z) bo'lsin"),
    ("lower", lambda v: any(c.islower() for c in v), "Kamida bitta kichik harf (a–z) bo'lsin"),
    ("digit", lambda v: any(c.isdigit() for c in v), "Kamida bitta raqam (0–9) bo'lsin"),
    ("symbol", lambda v: any(not c.isalnum() and not c.isspace() for c in v), "Kamida bitta belgi (! @ # - _ . kabi) bo'lsin"),
)


def _check_password(v: str) -> str:
    for _key, test, msg in PW_RULES:
        if not test(v):
            raise ValueError(msg.replace("{n}", str(PASSWORD_MIN)))
    if v.lower() in COMMON_PASSWORDS or len(set(v)) <= 4:
        raise ValueError("Parol juda keng tarqalgan — boshqasini tanlang")
    return v


class RegisterIn(Base):
    full_name: str = Field(min_length=3, max_length=80)
    email: str = Field(max_length=120)
    phone: str = Field(max_length=20)
    password: str = Field(min_length=PASSWORD_MIN, max_length=128)
    accept_terms: bool
    region: Optional[str] = Field(default=None, max_length=40)
    district: Optional[str] = Field(default=None, max_length=60)
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
        self.region, self.district = _check_place(self.region, self.district, required=True)
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


class ResetCheckIn(Base):
    login: str = Field(min_length=3, max_length=120)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


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
    district: Optional[str] = Field(default=None, max_length=60)
    _phone = field_validator("phone")(classmethod(lambda cls, v: _check_phone(v)))

    @model_validator(mode="after")
    def _place(self):
        self.region, self.district = _check_place(self.region, self.district, required=False)
        return self


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
    features: list[str] = Field(default_factory=list, max_length=30)
    city: str = Field(min_length=2, max_length=40)            # viloyat (hudud)
    district: Optional[str] = Field(default=None, max_length=60)
    description: Optional[str] = Field(default=None, max_length=2000)
    price_per_day: int = Field(ge=10_000, le=50_000_000)
    deposit: int = Field(default=0, ge=0, le=100_000_000)
    min_days: int = Field(default=1, ge=1, le=60)
    max_days: int = Field(default=30, ge=1, le=90)
    km_limit: Optional[int] = Field(default=None, ge=50, le=2000)
    delivery_price: Optional[int] = Field(default=None, ge=0, le=5_000_000)
    is_active: bool = True
    # v7: joylashuv (olib ketish nuqtasi), davlat raqami, yoqilg'i va probeg qoidalari, hujjat talabi
    lat: Optional[float] = Field(default=None, ge=37.0, le=46.0)       # O'zbekiston chegarasi atrofida
    lng: Optional[float] = Field(default=None, ge=55.0, le=74.0)
    address: Optional[str] = Field(default=None, max_length=160)
    plate: str = Field(min_length=6, max_length=14)          # v9: davlat raqami majburiy
    fuel_policy: Literal["same", "full"] = "same"
    tank_l: Optional[int] = Field(default=None, ge=10, le=200)
    fuel_price: Optional[int] = Field(default=None, ge=1000, le=100_000)
    extra_km_price: Optional[int] = Field(default=None, ge=0, le=100_000)
    require_docs: bool = False
    fuel_per_100: Optional[float] = Field(default=None, ge=2, le=40)    # litr / 100 km (elektr uchun kVt·soat)
    # Uzoq muddat chegirmasi: {"3": 5, "7": 10, "30": 20} — shuncha kundan boshlab kunlik narx shuncha foiz arzon
    discounts: dict[str, int] = Field(default_factory=dict, max_length=4)
    tech_passport: Optional[str] = Field(default=None, max_length=14)

    @field_validator("discounts")
    @classmethod
    def _discounts(cls, v: dict) -> dict:
        out = {}
        for k, pct in v.items():
            if str(k) not in ("3", "7", "14", "30") or not isinstance(pct, int) or not 0 <= pct <= 50:
                raise ValueError("Chegirma 0–50% oralig'ida bo'lishi kerak")
            if pct:
                out[str(k)] = pct
        return out

    @field_validator("tech_passport")
    @classmethod
    def _tp(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        v = re.sub(r"[^0-9A-Za-z]", "", v).upper()
        if not re.fullmatch(r"[A-Z]{3}\d{7}", v):
            raise ValueError("Texpasportni AAF1234567 ko'rinishida yozing")
        return v

    @field_validator("plate")
    @classmethod
    def _plate(cls, v: str) -> str:
        v = re.sub(r"[^0-9A-Za-z]", "", v).upper()
        if not re.fullmatch(r"\d{2}[A-Z]\d{3}[A-Z]{2}|\d{2}\d{3}[A-Z]{3}", v):
            raise ValueError("Davlat raqamini 01A123BC yoki 01123ABC ko'rinishida yozing")
        return v

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
        self.city, self.district = _check_place(self.city, self.district, required=False)
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
    # v7: joylashuv yuborish (lat/lng) — xabar xaritada ko'rinadi
    kind: Literal["text", "location"] = "text"
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def _loc(self):
        if self.kind == "location" and (self.lat is None or self.lng is None):
            raise ValueError("Joylashuv aniqlanmadi")
        if self.kind == "text":
            self.lat = self.lng = None
        return self


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
    action: Optional[Literal["hide_car", "delete_review", "block_user", "warn_user"]] = None
    note: Optional[str] = Field(None, max_length=1000)


class ImageOrderIn(Base):
    ids: list[int] = Field(min_length=1, max_length=20)


class ImageLabelIn(Base):
    label: Literal["front", "back", "side", "interior", "dashboard", "trunk", "other"]


class PayoutIn(Base):
    owner_id: int
    amount: int = Field(gt=0, le=10_000_000_000)
    note: Optional[str] = Field(default=None, max_length=200)


class PayoutRequestIn(Base):
    """Owner pul yechish so'rovi. To'liq karta raqami qabul qilinmaydi — faqat oxirgi 4 raqam (tekshirish uchun)."""
    amount: int = Field(gt=0, le=10_000_000_000)
    method: Literal["card", "bank", "cash"]
    card_last4: Optional[str] = Field(default=None, pattern=r"^[0-9]{4}$")
    note: Optional[str] = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _card(self):
        if self.method == "card" and not self.card_last4:
            raise ValueError("Karta raqamining oxirgi 4 raqamini kiriting")
        if self.method != "card":
            self.card_last4 = None
        return self


class FeeSettlementIn(Base):
    owner_id: int
    amount: int = Field(gt=0, le=10_000_000_000)
    from_balance: bool = False
    note: Optional[str] = Field(default=None, max_length=200)


class PayoutDecisionIn(Base):
    note: Optional[str] = Field(default=None, max_length=300)


AdvisorPurpose = Literal["city", "family", "trip", "mountain", "business", "event", "cargo"]
AdvisorPriority = Literal["economy", "comfort", "safety", "prestige", "price"]


class AdvisorIn(Base):
    """Maslahatchi: ijarachi o'z xohishlarini kiritadi, tizim mos avtomobillarni sabablari bilan tavsiya qiladi."""
    purpose: AdvisorPurpose = "city"
    passengers: int = Field(default=2, ge=1, le=15)
    luggage: Literal["none", "small", "medium", "large"] = "small"
    budget_max: Optional[int] = Field(default=None, gt=0, le=100_000_000)
    city: Optional[str] = Field(default=None, max_length=60)
    district: Optional[str] = Field(default=None, max_length=60)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    transmission: Optional[Transmission] = None
    experience: Literal["new", "normal"] = "normal"
    priorities: list[AdvisorPriority] = Field(default_factory=list, max_length=3)
    features: list[str] = Field(default_factory=list, max_length=8)
    delivery: bool = False

    @field_validator("features")
    @classmethod
    def _feats(cls, v):
        bad = [f for f in v if f not in FEATURES]
        if bad:
            raise ValueError("Noma'lum qulaylik")
        return list(dict.fromkeys(v))

    @field_validator("priorities")
    @classmethod
    def _prio(cls, v):
        return list(dict.fromkeys(v))

    @model_validator(mode="after")
    def _dates(self):
        if bool(self.start_date) != bool(self.end_date):
            raise ValueError("Ikkala sanani ham tanlang yoki ikkalasini ham bo'sh qoldiring")
        if self.start_date and self.end_date < self.start_date:
            raise ValueError("Tugash sanasi boshlanish sanasidan oldin bo'lmasligi kerak")
        self.city, self.district = _check_place(self.city, self.district, required=False)
        return self


DisputeType = Literal["damage", "no_show", "late_return", "deposit", "not_as_described", "payment", "fuel_mileage", "other"]


class DisputeIn(Base):
    booking_id: int
    type: DisputeType
    description: str = Field(min_length=20, max_length=2000)
    amount: Optional[int] = Field(default=None, ge=0, le=500_000_000)


class DisputeReplyIn(Base):
    text: str = Field(min_length=5, max_length=2000)


class DisputeResolveIn(Base):
    outcome: Literal["favor_opener", "favor_other", "split", "rejected"]
    note: str = Field(min_length=5, max_length=2000)
    compensation: Optional[int] = Field(default=None, ge=0, le=500_000_000)
    block_user_id: Optional[int] = None


class ChannelTestIn(Base):
    channel: Literal["sms", "email"]
    to: str = Field(min_length=5, max_length=120)


class AdminUserPatch(Base):
    is_active: bool


class AdminUserAction(Base):
    action: Literal["block", "unblock", "warn", "note", "verify_email", "unverify_email", "verify_phone", "unverify_phone",
                    "logout_all", "hide_cars", "restore_cars"]
    reason: Optional[str] = Field(None, max_length=1000)

    @model_validator(mode="after")
    def _need_reason(self):
        if self.action in ("block", "warn", "note") and len((self.reason or "").strip()) < 3:
            raise ValueError("Sababini yozing (kamida 3 belgi)")
        return self


class AdminProfileIn(Base):
    """Admin foydalanuvchi profilini tuzatadi (foydalanuvchi tushunmasa yoki xato yozgan bo'lsa)."""
    full_name: str = Field(min_length=3, max_length=80)
    email: str = Field(max_length=120)
    phone: Optional[str] = Field(default=None, max_length=20)
    region: Optional[str] = Field(default=None, max_length=40)
    district: Optional[str] = Field(default=None, max_length=60)
    lang: Literal["uz", "ru", "en"] = "uz"
    show_phone: bool = True
    reason: Optional[str] = Field(default=None, max_length=300)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip()
        if not EMAIL_RE.match(v):
            raise ValueError("Email manzil noto'g'ri")
        return v.lower()

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        return _check_phone(v) if v and v.strip() else None

    @model_validator(mode="after")
    def _place(self):
        self.region, self.district = _check_place(self.region, self.district, required=False)
        return self


class AdminPasswordIn(Base):
    mode: Literal["temp", "email"]


class AdminBookingCancel(Base):
    reason: str = Field(min_length=3, max_length=1000)
    full_refund: bool = False


class AdminCarPatch(Base):
    is_approved: Optional[bool] = None
    # v9: admin texpasport/raqam va egasining hujjatlarini solishtirib, egalikni tasdiqlaydi
    ownership_status: Optional[Literal["none", "verified", "rejected"]] = None


class SettingsIn(Base):
    commission_percent: float = Field(ge=0, le=30)
