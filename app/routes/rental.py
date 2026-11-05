"""Ijara jarayoni: elektron shartnoma va qabul-topshirish dalolatnomasi.

ELEKTRON SHARTNOMA
  * Owner bronni tasdiqlashi bilan shartnoma avtomatik tuziladi: admin tahrirlagan shablonga bron, mashina va
    tomonlar ma'lumotlari qo'yiladi. Matn shu paytda "muzlatiladi" va uning SHA-256 xeshi saqlanadi.
  * Har bir tomon emailiga bir martalik kod keladi; kodni kiritib "roziman" desa — imzolangan hisoblanadi
    (vaqti va IP manzili yoziladi). Bu oddiy elektron imzo: kim, qachon, qaysi matnga rozi bo'lgani isbotlanadi.
  * Ikkala tomon imzolagach admin tekshirib tasdiqlaydi: shartnomaga elektron muhr va QR-kod qo'yiladi.
    QR kod ochiq tekshirish sahifasiga olib boradi: shartnoma haqiqiyligini va matn o'zgarmaganini istalgan odam tekshira oladi.

QABUL-TOPSHIRISH DALOLATNOMASI
  * Mashina berilganda (pickup) va qaytarilganda (return): probeg, yoqilg'i darajasi, tozaligi, shikast va rasmlar.
  * Bir tomon to'ldiradi, ikkinchisi tasdiqlaydi yoki e'tirozini yozadi.
  * Qaytarishda tizim hisoblaydi: yoqilg'i kamomadi (mashina qoidasi bo'yicha) va limitdan ortiq km uchun qo'shimcha summa;
    yangi shikast bo'lsa — rasmlar bilan nizo ochish taklif qilinadi. Bu summa depozitdan ushlanishi mumkin.
"""
import hashlib
import hmac
import json
import secrets
from datetime import date, datetime, timedelta, timezone

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.routing import Route

from .. import channels
from ..config import settings
from ..db import get_db, get_setting, one, rows, transaction
from ..i18n import tr
from ..schemas import Base
from ..security import client_ip, new_code, require
from ..utils import audit, car_title, notify, ok, parse_body, path_int, q_str, today
from .bookings import BOOKING_SELECT

from pydantic import Field

DEFAULT_TEMPLATE = """# AVTOMOBILNI IJARAGA BERISH SHARTNOMASI № {number}
{city}, {date}

Bir tomondan, avtomobil egasi {owner_name} (keyingi o'rinlarda — «Ijaraga beruvchi»), ikkinchi tomondan, {renter_name} (keyingi o'rinlarda — «Ijarachi»), {platform} onlayn platformasi orqali ushbu shartnomani quyidagilar haqida tuzdilar:

## 1. Shartnoma predmeti
1.1. Ijaraga beruvchi Ijarachiga quyidagi avtomobilni haydovchisiz vaqtincha egalik qilish va foydalanish uchun beradi: {car}, {car_year} yil, rangi: {car_color}, davlat raqami: {plate}, kuzov turi: {body}, yoqilg'i: {fuel}.
1.2. Avtomobil Ijaraga beruvchiga tegishli bo'lib, u avtomobilni ijaraga berishga haqli ekanini kafolatlaydi.
1.3. Avtomobil faqat shaxsiy maqsadda, O'zbekiston Respublikasi hududida ishlatiladi. Taksi, yuk tashish xizmati, ko'rsatuv haydash, musobaqa va o'quv haydash uchun foydalanish taqiqlanadi.
1.4. Platformadagi e'lon ma'lumotlarini (rasm, yil, probeg, jihozlar) Ijaraga beruvchi kiritgan va ular uchun u javobgar. Ijarachi avtomobilni qabul qilishda texnik pasportni, davlat raqamini, kuzov (VIN) raqamini va probegni e'lon hamda ushbu shartnoma bilan solishtiradi va qabul-topshirish dalolatnomasida «tekshirdim, qabul qildim» deb tasdiqlaydi.
1.5. Agar avtomobil yoki uning hujjatlari e'londagi ma'lumotlarga mos kelmasa (boshqa avtomobil, soxta yoki muddati o'tgan hujjat, egasi boshqa shaxs), Ijarachi avtomobilni qabul qilmaslikka haqli. Bunday holda shartnoma bekor qilinadi, Ijarachiga to'langan barcha summa to'liq qaytariladi, Ijaraga beruvchining e'loni esa platforma tomonidan to'xtatiladi.

## 2. Ijara muddati va avtomobilni topshirish
2.1. Ijara muddati: {start} dan {end} gacha ({days} kun).
2.2. Avtomobil topshiriladigan joy: {address}.
2.3. Avtomobil qabul-topshirish dalolatnomasi asosida beriladi va qaytariladi. Dalolatnomada probeg, yoqilg'i darajasi, tashqi va ichki holat rasmlar bilan qayd etiladi. Dalolatnoma ushbu shartnomaning ajralmas qismi hisoblanadi.
2.4. Avtomobilni kechiktirib qaytarish oldindan kelishilmagan bo'lsa, har bir kechikkan sutka uchun bir kunlik ijara haqi undiriladi.

## 3. Ijara haqi va to'lov tartibi
3.1. Kunlik ijara haqi: {price_per_day}. Ijara haqi jami (uzoq muddat chegirmasi hisobga olingan): {rent}. Yetkazib berish: {delivery}. Umumiy summa: {total}.
3.2. To'lov platforma orqali onlayn (Click, Payme) yoki avtomobil topshirilayotganda joyida amalga oshiriladi.
3.3. Platforma xizmat haqi ({commission_pct}%) Ijaraga beruvchi oladigan summadan ushlanadi va Ijarachi uchun qo'shimcha to'lov emas.

## 4. Garov puli (depozit)
4.1. Ijarachi avtomobilni olishda {deposit} miqdorida qaytariladigan garov puli qoldiradi.
4.2. Garov puli avtomobil shikastsiz, kelishilgan yoqilg'i darajasida va o'z vaqtida qaytarilganda to'liq qaytariladi.
4.3. Garovdan faqat qabul-topshirish dalolatnomasi bilan tasdiqlangan zarar, yoqilg'i kamomadi, ortiqcha probeg yoki jarimalar ushlab qolinishi mumkin; ushlangan summa asoslanishi shart.

## 5. Ijaraga beruvchining majburiyatlari
5.1. Avtomobilni texnik soz, toza, hujjatlari (texnik pasport, amaldagi OSAGO sug'urtasi) bilan topshirish.
5.2. Avtomobilning yashirin nuqsonlari haqida oldindan xabar berish.
5.3. Avtomobil Ijarachining aybisiz buzilsa — uni almashtirish yoki to'langan pulni foydalanilmagan kunlar uchun qaytarish.

## 5A. Ijara davomida avtomobil buzilsa
5A.1. Ijarachi nosozlikni sezgan zahoti harakatni to'xtatadi va Ijaraga beruvchiga (platforma chat yoki telefon orqali) xabar beradi; nosoz avtomobilda harakatni davom ettirib, zararni oshirmaydi.
5A.2. Tabiiy eskirish, zavod nuqsoni yoki Ijarachiga bog'liq bo'lmagan sabab bilan buzilsa — ta'mir xarajatini Ijaraga beruvchi to'laydi. U 24 soat ichida avtomobilni tuzatadi yoki shunga teng boshqa avtomobil beradi; buning iloji bo'lmasa, foydalanilmagan kunlar haqi to'liq qaytariladi, ta'mirda turgan vaqt esa ijara muddatiga kiritilmaydi.
5A.3. Kichik ta'mirni (lampochka, g'ildirak teshilishi, akkumulyator kabi) Ijarachi Ijaraga beruvchining roziligi bilan o'zi qildirishi mumkin; chek yoki servis hisob-varag'i asosida xarajat Ijaraga beruvchi tomonidan qaytariladi.
5A.4. Ijarachining aybi bilan (qoidabuzarlik, noto'g'ri yoqilg'i, beparvolik) yuzaga kelgan buzilish ta'mirini Ijarachi to'laydi; bu holda ta'mirda turgan kunlar uchun ham kunlik haq saqlanib qoladi.

## 6. Ijarachining majburiyatlari
6.1. Amaldagi haydovchilik guvohnomasiga ega bo'lish ({renter_license}, toifa: {renter_license_cat}) va avtomobilni faqat o'zi boshqarish. Boshqa shaxsga topshirish faqat Ijaraga beruvchining yozma roziligi bilan.
6.2. Yo'l harakati qoidalariga rioya qilish; alkogol, giyohvand yoki kuchli dori ta'sirida boshqarmaslik.
6.3. Avtomobilni ehtiyotkorlik bilan ishlatish, salonda chekmaslik, uy hayvonlarini faqat ruxsat bo'lsa olib yurish.
6.4. Avtomobilni subijaraga bermaslik, garovga qo'ymaslik, konstruksiyasini o'zgartirmaslik.
6.5. Ijara davrida qayd etilgan YHQ jarimalari (shu jumladan kamera jarimalari) Ijarachi zimmasida.

## 7. Yoqilg'i va probeg
7.1. Yoqilg'i qoidasi: {fuel_policy_text}. Kamomad uchun 1 litr — {fuel_price} hisobida haq olinadi.
7.2. Kunlik probeg chegarasi: {km_limit}. Chegaradan oshgan har bir km uchun {extra_km_price} to'lanadi.

## 8. Shikast, yo'l-transport hodisasi va javobgarlik
8.1. YTH, o'g'irlik yoki shikast holatida Ijarachi darhol YPX (102), Ijaraga beruvchi va platformaga xabar beradi va hodisa joyini rasmga oladi.
8.2. Ijarachi aybi bilan yetkazilgan, sug'urta qoplamagan zararni Ijarachi qoplaydi. Zarar miqdori dalolatnoma, rasmlar va servis hisob-kitobi asosida aniqlanadi.
8.3. Tabiiy eskirish va Ijarachiga bog'liq bo'lmagan texnik nosozliklar uchun Ijarachi javobgar emas.

## 9. Shartnomani bekor qilish va muddatidan oldin tugatish
9.1. Ijarachi ijara boshlanishidan 3 va undan ortiq kun oldin bekor qilsa — to'langan summa to'liq qaytariladi; 1–2 kun oldin — 50% qaytariladi; ijara kuni yoki keyin — qaytarilmaydi.
9.2. Ijaraga beruvchi tasdiqlangan bronni bekor qilsa — Ijarachiga to'langan summa to'liq qaytariladi; ijara boshlanishiga 2 kundan kam qolganda bekor qilish takrorlansa, platforma e'lon reytingini pasaytirishi yoki uni to'xtatishi mumkin.
9.3. Ijarachi avtomobilni muddatidan oldin qaytarsa: foydalanilgan kunlar to'liq haq bilan hisoblanadi (uzoq muddat chegirmasi faqat haqiqatda foydalanilgan kunlar soniga mos qayta hisoblanadi); foydalanilmagan kunlar haqidan Ijaraga beruvchining kompensatsiyasi sifatida 1 kunlik ijara haqi ushlab qolinadi, qolgani Ijarachiga qaytariladi. Ijaraga beruvchi avtomobilni boshqa mijozga bera olsa, ushlab qolingan kompensatsiya ham qaytariladi.
9.4. Ijaraga beruvchi avtomobilni muddatidan oldin qaytarib olishi faqat Ijarachi shartnomani qo'pol buzganda (6-bo'lim) mumkin; aks holda foydalanilmagan kunlar haqi to'liq qaytariladi va Ijarachiga 1 kunlik ijara haqi miqdorida kompensatsiya to'lanadi.
9.5. Tomonlardan biri shartnoma shartlarini qo'pol buzsa, ikkinchi tomon uni bir tomonlama bekor qilishga haqli.

## 10. Nizolarni hal qilish
10.1. Nizolar avvalo muzokara va platformaning nizolarni ko'rib chiqish xizmati orqali hal qilinadi.
10.2. Kelishuvga erishilmasa, nizo O'zbekiston Respublikasi qonunchiligiga muvofiq sudda ko'rib chiqiladi.

## 11. Elektron shaklda tuzish va kuchga kirish
11.1. Shartnoma elektron shaklda tuziladi. Har bir tomon o'z emailiga yuborilgan bir martalik kodni kiritib, shartlarga roziligini tasdiqlaydi (oddiy elektron imzo). Imzolash vaqti va IP manzil qayd etiladi.
11.2. Shartnoma ikkala tomon imzolagan paytdan kuchga kiradi va majburiyatlar to'liq bajarilguncha amal qiladi. Platforma administratori tekshirgach, shartnomaga elektron muhr va QR-kod qo'yiladi.
11.3. Shartnomaning haqiqiyligi va matni o'zgartirilmaganligini QR-kod orqali tekshirish mumkin.
11.4. {platform} platformasi tomonlarni bog'lovchi vositachi hisoblanadi va avtomobil egasi emas.

## 12. Tomonlar ma'lumotlari
Ijaraga beruvchi: {owner_name}, tel.: {owner_phone}, email: {owner_email}.
Ijarachi: {renter_name}, tel.: {renter_phone}, email: {renter_email}, shaxsni tasdiqlovchi hujjat: {renter_id}.
"""

PLACEHOLDERS = ("number", "date", "city", "address", "platform", "owner_name", "owner_phone", "owner_email", "renter_name", "renter_phone",
                "renter_email", "renter_license", "renter_license_cat", "renter_id", "car", "car_year", "car_color", "plate", "body",
                "fuel", "start", "end", "days", "price_per_day", "rent", "delivery", "total", "deposit", "commission_pct",
                "fuel_policy_text", "fuel_price", "km_limit", "extra_km_price")

BODY_UZ = {"sedan": "sedan", "hatchback": "xetchbek", "crossover": "krossover", "suv": "yo'ltanlamas", "minivan": "miniven",
           "pickup": "pikap", "coupe": "kupe"}
FUEL_UZ = {"petrol": "benzin", "gas": "gaz (metan/propan)", "diesel": "dizel", "hybrid": "gibrid", "electric": "elektr"}


def som(n) -> str:
    return f"{int(n or 0):,}".replace(",", " ") + " so'm"


def dmy(iso: str) -> str:
    return date.fromisoformat(iso[:10]).strftime("%d.%m.%Y")


def contract_number(booking_id: int, created: str | None = None) -> str:
    return f"CR-{(created or today().isoformat())[:4]}-{booking_id:06d}"


def render_contract(db, b: dict, number: str) -> str:
    from .trust import docs_state
    car = one(db.execute("SELECT * FROM cars WHERE id = ?", (b["car_id"],)))
    owner = one(db.execute("SELECT full_name, phone, email FROM users WHERE id = ?", (car["owner_id"],)))
    renter = one(db.execute("SELECT full_name, phone, email FROM users WHERE id = ?", (b["renter_id"],)))
    docs = docs_state(db, b["renter_id"])["docs"]
    lic, idc = docs.get("license") or {}, docs.get("id_card") or {}
    dash = "—"
    values = {
        "number": number, "date": dmy(today().isoformat()), "city": car["city"], "platform": "CarRent",
        "address": car["address"] or ", ".join(x for x in (car["district"], car["city"]) if x),
        "owner_name": owner["full_name"], "owner_phone": owner["phone"] or dash, "owner_email": owner["email"],
        "renter_name": renter["full_name"], "renter_phone": renter["phone"] or dash, "renter_email": renter["email"],
        "renter_license": f"№ {lic['number_mask']}" if lic.get("number_mask") else "guvohnoma ma'lumoti platformada tasdiqlanmagan",
        "renter_license_cat": lic.get("categories") or dash,
        "renter_id": idc.get("number_mask") or dash,
        "car": f"{car['brand']} {car['model']}", "car_year": car["year"], "car_color": car["color"] or dash, "plate": car["plate"] or dash,
        "body": BODY_UZ.get(car["body_type"], car["body_type"]), "fuel": FUEL_UZ.get(car["fuel"], car["fuel"]),
        "start": dmy(b["start_date"]), "end": dmy(b["end_date"]), "days": b["days"], "price_per_day": som(b["price_per_day"]),
        "rent": som(b["total_price"] - (b["delivery"] or 0)), "delivery": som(b["delivery"]) if b["delivery"] else "yo'q",
        "total": som(b["total_price"]), "deposit": som(b["deposit"]) if b["deposit"] else "olinmaydi (0 so'm)",
        "commission_pct": f"{b['commission_bps'] / 100:g}",
        "fuel_policy_text": "to'la bak bilan olinadi va to'la bak bilan qaytariladi" if car["fuel_policy"] == "full"
                            else "qanday darajada olingan bo'lsa, shunday darajada qaytariladi",
        "fuel_price": som(car["fuel_price"]) if car["fuel_price"] else "yoqilg'ining shu kundagi bozor narxi",
        "km_limit": f"{car['km_limit']} km/kun" if car["km_limit"] else "cheklanmagan",
        "extra_km_price": som(car["extra_km_price"]) if car["extra_km_price"] else "kelishilgan narx",
    }
    text = get_setting(db, "contract_template", "") or DEFAULT_TEMPLATE
    for k, v in values.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def ensure_contract(db, booking_id: int) -> dict | None:
    """Tasdiqlangan/yakunlangan bron uchun shartnoma bo'lmasa — yaratadi (bron paytidagi ma'lumotlar bilan)."""
    c = one(db.execute("SELECT * FROM contracts WHERE booking_id = ?", (booking_id,)))
    if c:
        return c
    b = one(db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)))
    if not b or b["status"] not in ("approved", "completed"):
        return None
    number = contract_number(booking_id, b["created_at"])
    body = render_contract(db, b, number)
    db.execute("INSERT INTO contracts (booking_id, number, body, body_hash, verify_token) VALUES (?, ?, ?, ?, ?)",
               (booking_id, number, body, hashlib.sha256(body.encode()).hexdigest(), secrets.token_urlsafe(18)))
    owner_id = db.execute("SELECT owner_id FROM cars WHERE id = ?", (b["car_id"],)).fetchone()[0]
    for uid, mode in ((b["renter_id"], "renter"), (owner_id, "owner")):
        notify(db, uid, "contract_ready", f"/contract.html?booking={booking_id}", mode=mode, number=number)
    return one(db.execute("SELECT * FROM contracts WHERE booking_id = ?", (booking_id,)))


def _booking_for(db, booking_id: int, user: dict) -> dict:
    b = one(db.execute(BOOKING_SELECT + " WHERE b.id = ?", (booking_id,)))
    if not b:
        raise HTTPException(404, tr("Bron topilmadi"))
    if user["role"] != "admin" and user["id"] not in (b["renter_id"], b["owner_id"]):
        raise HTTPException(403, tr("Bu bron sizga tegishli emas"))
    return b


def _contract_payload(db, c: dict, b: dict, user: dict | None) -> dict:
    status = c["status"]
    if b["status"] in ("cancelled", "rejected") and status != "approved":
        status = "cancelled"
    approver = one(db.execute("SELECT full_name FROM users WHERE id = ?", (c["approved_by"],))) if c["approved_by"] else None
    car = one(db.execute("SELECT brand, model, year, color, plate, city, district, address, lat, lng FROM cars WHERE id = ?", (b["car_id"],)))
    out = {
        "id": c["id"], "number": c["number"], "body": c["body"], "body_hash": c["body_hash"], "status": status,
        "intact": hashlib.sha256(c["body"].encode()).hexdigest() == c["body_hash"],
        "renter_signed_at": c["renter_signed_at"], "owner_signed_at": c["owner_signed_at"],
        "approved_at": c["approved_at"], "approved_by": approver["full_name"] if approver else None, "created_at": c["created_at"],
        "verify_path": f"/verify.html?n={c['number']}&t={c['verify_token']}",
        "booking": {"id": b["id"], "status": b["status"], "start_date": b["start_date"], "end_date": b["end_date"], "days": b["days"],
                    "total_price": b["total_price"], "renter_id": b["renter_id"], "owner_id": b["owner_id"],
                    "renter_name": b["renter_name"], "owner_name": b["owner_name"], "cover": b["cover"], "car_id": b["car_id"]},
        "car": car,
    }
    if user:
        out["my_role"] = "renter" if user["id"] == b["renter_id"] else "owner" if user["id"] == b["owner_id"] else "admin"
        out["can_sign"] = (status == "pending" and out["my_role"] in ("renter", "owner")
                           and not c[f"{out['my_role']}_signed_at"])
    return out


# ---------------- Shartnoma endpointlari ----------------
@require()
async def booking_contract(request: Request):
    bid = path_int(request)
    with get_db() as db:
        b = _booking_for(db, bid, request.state.user)
        with transaction(db):
            c = ensure_contract(db, bid)
        if not c:
            raise HTTPException(404, tr("Shartnoma bron tasdiqlangandan keyin tuziladi"))
        return ok(_contract_payload(db, c, b, request.state.user))


@require()
async def contract_sign_start(request: Request):
    cid = path_int(request)
    user = request.state.user
    with get_db() as db:
        c = one(db.execute("SELECT * FROM contracts WHERE id = ?", (cid,)))
        if not c:
            raise HTTPException(404, tr("Shartnoma topilmadi"))
        b = _booking_for(db, c["booking_id"], user)
        p = _contract_payload(db, c, b, user)
        if not p.get("can_sign"):
            raise HTTPException(400, tr("Bu shartnomani hozir imzolab bo'lmaydi"))
        last = one(db.execute("SELECT created_at FROM contract_codes WHERE contract_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1", (cid, user["id"])))
        if last:
            age = (datetime.now(timezone.utc).replace(tzinfo=None) - datetime.fromisoformat(last["created_at"])).total_seconds()
            if age < settings.CODE_RESEND_SEC:
                raise HTTPException(429, tr("Kodni qayta yuborish uchun {n} soniya kuting", n=int(settings.CODE_RESEND_SEC - age) + 1))
        code = new_code()
        expires = (datetime.now(timezone.utc) + timedelta(minutes=settings.CODE_TTL_MIN)).strftime("%Y-%m-%d %H:%M:%S")
        db.execute("UPDATE contract_codes SET used_at = datetime('now') WHERE contract_id = ? AND user_id = ? AND used_at IS NULL", (cid, user["id"]))
        db.execute("INSERT INTO contract_codes (contract_id, user_id, code_hash, expires_at) VALUES (?, ?, ?, ?)",
                   (cid, user["id"], _code_hash(code, cid, user["id"]), expires))
        try:
            via = channels.send("email", user["email"], "sign_contract", user.get("lang") or "uz", db=db,
                                number=c["number"], code=code, ttl=settings.CODE_TTL_MIN)
        except channels.DeliveryUnavailable:
            raise HTTPException(503, tr("Email xizmati sozlanmagan. Administratorga murojaat qiling"))
    return ok({"via": via, "to": user["email"], "ttl_sec": settings.CODE_TTL_MIN * 60, "resend_sec": settings.CODE_RESEND_SEC,
               "dev_inbox": via == "dev_inbox"})


def _code_hash(code: str, cid: int, uid: int) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f"contract:{cid}:{uid}:{code}".encode(), hashlib.sha256).hexdigest()


class SignIn(Base):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    agree: bool


@require()
async def contract_sign(request: Request):
    cid = path_int(request)
    data = await parse_body(request, SignIn)
    if not data.agree:
        raise HTTPException(400, tr("Shartnoma shartlariga roziligingizni belgilang"))
    user = request.state.user
    with get_db() as db:
        c = one(db.execute("SELECT * FROM contracts WHERE id = ?", (cid,)))
        if not c:
            raise HTTPException(404, tr("Shartnoma topilmadi"))
        b = _booking_for(db, c["booking_id"], user)
        p = _contract_payload(db, c, b, user)
        if not p.get("can_sign"):
            raise HTTPException(400, tr("Bu shartnomani hozir imzolab bo'lmaydi"))
        rec = one(db.execute("SELECT * FROM contract_codes WHERE contract_id = ? AND user_id = ? AND used_at IS NULL ORDER BY id DESC LIMIT 1",
                             (cid, user["id"])))
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if not rec or datetime.fromisoformat(rec["expires_at"]) < now or rec["attempts"] >= settings.CODE_MAX_ATTEMPTS:
            raise HTTPException(400, tr("Kod noto'g'ri yoki muddati tugagan. Yangi kod so'rang"))
        if not hmac.compare_digest(rec["code_hash"], _code_hash(data.code, cid, user["id"])):
            db.execute("UPDATE contract_codes SET attempts = attempts + 1 WHERE id = ?", (rec["id"],))
            raise HTTPException(400, tr("Kod noto'g'ri. Qolgan urinishlar: {n}", n=max(0, settings.CODE_MAX_ATTEMPTS - rec["attempts"] - 1)))
        role = p["my_role"]
        with transaction(db):
            if not db.execute("UPDATE contract_codes SET used_at = datetime('now') WHERE id = ? AND used_at IS NULL", (rec["id"],)).rowcount:
                raise HTTPException(400, tr("Kod noto'g'ri yoki muddati tugagan. Yangi kod so'rang"))
            db.execute(f"UPDATE contracts SET {role}_signed_at = datetime('now'), {role}_sign_ip = ? WHERE id = ?", (client_ip(request), cid))
            c = one(db.execute("SELECT * FROM contracts WHERE id = ?", (cid,)))
            other = b["owner_id"] if role == "renter" else b["renter_id"]
            if c["renter_signed_at"] and c["owner_signed_at"]:
                db.execute("UPDATE contracts SET status = 'signed' WHERE id = ?", (cid,))
                for a in db.execute("SELECT id FROM users WHERE role = 'admin' AND is_active = 1").fetchall():
                    notify(db, a[0], "contract_to_approve", "/admin.html#contracts", mode="admin", number=c["number"])
            notify(db, other, "contract_signed_by", f"/contract.html?booking={b['id']}", mode="owner" if role == "renter" else "renter",
                   actor_id=user["id"], number=c["number"])
            audit(db, request, "contract_signed", "contract", cid, role=role)
            c = one(db.execute("SELECT * FROM contracts WHERE id = ?", (cid,)))
        return ok(_contract_payload(db, c, b, user))


@require("admin")
async def admin_contracts(request: Request):
    status = q_str(request, "status") or "signed"
    if status not in ("pending", "signed", "approved", "all"):
        raise HTTPException(400, tr("Filtr qiymati noto'g'ri"))
    with get_db() as db:
        where = "" if status == "all" else "WHERE k.status = ?"
        items = rows(db.execute(
            f"""SELECT k.id, k.number, k.status, k.renter_signed_at, k.owner_signed_at, k.approved_at, k.created_at, k.booking_id,
                       b.start_date, b.end_date, b.total_price, b.status AS booking_status, c.id AS car_id, c.brand, c.model, c.year,
                       (SELECT path FROM car_images i WHERE i.car_id = c.id ORDER BY position, id LIMIT 1) AS cover,
                       b.renter_id, ru.full_name AS renter_name, c.owner_id, ou.full_name AS owner_name
                FROM contracts k JOIN bookings b ON b.id = k.booking_id JOIN cars c ON c.id = b.car_id
                JOIN users ru ON ru.id = b.renter_id JOIN users ou ON ou.id = c.owner_id {where} ORDER BY k.id DESC LIMIT 200""",
            () if status == "all" else (status,)))
        counts = {s: n for s, n in db.execute("SELECT status, COUNT(*) FROM contracts GROUP BY status")}
    return ok({"items": items, "counts": counts})


@require("admin")
async def admin_approve_contract(request: Request):
    cid = path_int(request)
    with get_db() as db, transaction(db):
        c = one(db.execute("SELECT * FROM contracts WHERE id = ?", (cid,)))
        if not c:
            raise HTTPException(404, tr("Shartnoma topilmadi"))
        if c["status"] != "signed":
            raise HTTPException(400, tr("Avval ikkala tomon shartnomani imzolashi kerak"))
        if hashlib.sha256(c["body"].encode()).hexdigest() != c["body_hash"]:
            raise HTTPException(409, tr("Shartnoma matni o'zgartirilgan — tasdiqlab bo'lmaydi"))
        db.execute("UPDATE contracts SET status = 'approved', approved_by = ?, approved_at = datetime('now') WHERE id = ?",
                   (request.state.user["id"], cid))
        b = one(db.execute("SELECT b.id, b.renter_id, c.owner_id FROM bookings b JOIN cars c ON c.id = b.car_id WHERE b.id = ?", (c["booking_id"],)))
        for uid, mode in ((b["renter_id"], "renter"), (b["owner_id"], "owner")):
            notify(db, uid, "contract_approved", f"/contract.html?booking={b['id']}", mode=mode, number=c["number"])
        audit(db, request, "contract_approved", "contract", cid, number=c["number"])
    return ok({"id": cid, "status": "approved"})


@require("admin")
async def contract_template(request: Request):
    with get_db() as db:
        custom = get_setting(db, "contract_template", "")
    return ok({"template": custom or DEFAULT_TEMPLATE, "is_default": not custom, "placeholders": PLACEHOLDERS, "default": DEFAULT_TEMPLATE})


class TemplateIn(Base):
    template: str = Field(min_length=200, max_length=40000)


@require("admin")
async def save_contract_template(request: Request):
    data = await parse_body(request, TemplateIn)
    for must in ("{number}", "{renter_name}", "{owner_name}", "{car}", "{start}", "{end}", "{total}"):
        if must not in data.template:
            raise HTTPException(400, tr("Shablonda majburiy maydon yo'q: {f}", f=must))
    with get_db() as db:
        value = "" if data.template.strip() == DEFAULT_TEMPLATE.strip() else data.template
        db.execute("INSERT INTO settings (key, value, updated_at) VALUES ('contract_template', ?, datetime('now')) "
                   "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at", (value,))
        audit(db, request, "contract_template_saved", "settings", None)
    return ok({"saved": True})


async def verify_contract(request: Request):
    """Ochiq tekshirish (QR kod shu yerga olib keladi): shaxsiy ma'lumotlarsiz — raqam, holat, sanalar, mashina, xesh."""
    n, tok = q_str(request, "n", 40), q_str(request, "t", 60)
    with get_db() as db:
        c = one(db.execute("SELECT * FROM contracts WHERE number = ?", (n or "",)))
        if not c or not tok or not hmac.compare_digest(c["verify_token"], tok):
            raise HTTPException(404, tr("Shartnoma topilmadi"))
        b = one(db.execute(BOOKING_SELECT + " WHERE b.id = ?", (c["booking_id"],)))
        p = _contract_payload(db, c, b, None)
    initials = lambda name: " ".join((w[0] + ".") if i else w for i, w in enumerate((name or "").split()[:2]))
    return ok({"number": p["number"], "status": p["status"], "intact": p["intact"], "body_hash": p["body_hash"],
               "renter": initials(b["renter_name"]), "owner": initials(b["owner_name"]),
               "car": f"{b['brand']} {b['model']} {b['year']}", "start_date": b["start_date"], "end_date": b["end_date"],
               "renter_signed_at": p["renter_signed_at"], "owner_signed_at": p["owner_signed_at"], "approved_at": p["approved_at"],
               "created_at": p["created_at"]})


# ---------------- Qabul-topshirish dalolatnomasi ----------------
MAX_HANDOVER_PHOTOS = 8


def handover_calc(car: dict, b: dict, pick: dict | None, ret: dict | None) -> dict | None:
    """Qaytarishda qo'shimcha to'lov hisobi: yoqilg'i kamomadi va limitdan ortiq km. Shikast — alohida (nizo orqali)."""
    if not pick or not ret:
        return None
    used = max(0, ret["odometer_km"] - pick["odometer_km"])
    allowed = car["km_limit"] * b["days"] if car["km_limit"] else None
    over = max(0, used - allowed) if allowed is not None else 0
    km_charge = over * (car["extra_km_price"] or 0)
    target = 100 if car["fuel_policy"] == "full" else pick["fuel_pct"]
    fuel_short_pct = max(0, target - ret["fuel_pct"])
    liters = round(fuel_short_pct / 100 * car["tank_l"], 1) if car["tank_l"] else None
    fuel_charge = round(liters * car["fuel_price"]) if liters and car["fuel_price"] else 0
    new_damage = bool(ret["damage"]) and not bool(pick["damage"])
    total = km_charge + fuel_charge
    return {"km_used": used, "km_allowed": allowed, "km_over": over, "km_charge": km_charge,
            "fuel_policy": car["fuel_policy"], "fuel_target_pct": target, "fuel_short_pct": fuel_short_pct, "fuel_liters": liters,
            "fuel_charge": fuel_charge, "new_damage": new_damage, "dirty": not ret["clean"] and bool(pick["clean"]),
            "total": total, "deposit": b["deposit"], "from_deposit": min(total, b["deposit"] or 0),
            "rates_missing": (over > 0 and not car["extra_km_price"]) or (fuel_short_pct > 0 and not (car["tank_l"] and car["fuel_price"]))}


def _handovers(db, b: dict) -> dict:
    items = {h["kind"]: h for h in rows(db.execute(
        """SELECT h.*, u.full_name AS created_by_name, x.full_name AS confirmed_by_name FROM handovers h
           JOIN users u ON u.id = h.created_by LEFT JOIN users x ON x.id = h.confirmed_by WHERE h.booking_id = ?""", (b["id"],)))}
    for h in items.values():
        h["photos"] = [f"/api/files/{n}" for n in json.loads(h["photos"])]
    car = one(db.execute("SELECT km_limit, extra_km_price, fuel_policy, tank_l, fuel_price FROM cars WHERE id = ?", (b["car_id"],)))
    booking = {k: b[k] for k in ("id", "car_id", "brand", "model", "year", "cover", "start_date", "end_date", "days", "status", "deposit",
                                 "renter_id", "renter_name", "owner_id", "owner_name", "total_price")}
    return {"booking": booking, "pickup": items.get("pickup"), "return": items.get("return"), "car": car,
            "calc": handover_calc(car, b, items.get("pickup"), items.get("return")),
            "can_pickup_from": (date.fromisoformat(b["start_date"]) - timedelta(days=1)).isoformat()}


@require()
async def booking_handovers(request: Request):
    bid = path_int(request)
    with get_db() as db:
        b = _booking_for(db, bid, request.state.user)
        return ok(_handovers(db, b))


@require("user")
async def create_handover(request: Request):
    bid = path_int(request)
    user = request.state.user
    from .trust import remove_private, save_private_image
    async with request.form(max_files=MAX_HANDOVER_PHOTOS, max_fields=12) as form:
        kind = str(form.get("kind") or "")
        try:
            odo = int(str(form.get("odometer_km") or "").replace(" ", ""))
            fuel = int(str(form.get("fuel_pct") or ""))
        except ValueError:
            raise HTTPException(400, tr("Probeg va yoqilg'i darajasini kiriting"))
        clean = str(form.get("clean") or "1") in ("1", "true", "on")
        damage = str(form.get("damage") or "0") in ("1", "true", "on")
        notes = (str(form.get("notes") or "").strip() or None)
        if notes and len(notes) > 1000:
            notes = notes[:1000]
        files = [f for f in form.getlist("photos") if hasattr(f, "read")]
        if kind not in ("pickup", "return") or not 0 <= odo <= 2_000_000 or not 0 <= fuel <= 100:
            raise HTTPException(400, tr("Probeg va yoqilg'i darajasini kiriting"))
        if len(files) < 4:
            raise HTTPException(400, tr("Kamida 4 ta rasm yuklang: old, orqa, ikki yon tomon (salon va probeg ham tavsiya etiladi)"))
        if damage and not notes:
            raise HTTPException(400, tr("Shikastni izohda yozing: qayerda va qanday"))
        with get_db() as db:
            b = _booking_for(db, bid, user)
            if user["id"] not in (b["renter_id"], b["owner_id"]):
                raise HTTPException(403, tr("Bu bron sizga tegishli emas"))
            existing = _handovers(db, b)
            if b["status"] not in ("approved", "completed"):
                raise HTTPException(400, tr("Dalolatnoma faqat tasdiqlangan bron uchun to'ldiriladi"))
            if existing[kind]:
                raise HTTPException(409, tr("Bu dalolatnoma allaqachon to'ldirilgan"))
            if kind == "return" and not existing["pickup"]:
                raise HTTPException(400, tr("Avval mashinani topshirish dalolatnomasi to'ldirilishi kerak"))
            if kind == "pickup" and b["start_date"] > (today() + timedelta(days=1)).isoformat():
                raise HTTPException(400, tr("Topshirish dalolatnomasini ijara boshlanishiga 1 kun qolganda to'ldirish mumkin"))
            if kind == "return" and odo < existing["pickup"]["odometer_km"]:
                raise HTTPException(400, tr("Qaytarishdagi probeg olishdagidan kam bo'lishi mumkin emas"))
        names = []
        try:
            for f in files:
                names.append(save_private_image(await f.read(settings.MAX_IMAGE_MB * 1024 * 1024 + 1)))
        except HTTPException:
            remove_private(names)
            raise
    with get_db() as db, transaction(db):
        try:
            db.execute("INSERT INTO handovers (booking_id, kind, odometer_km, fuel_pct, clean, damage, notes, photos, created_by) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (bid, kind, odo, fuel, int(clean), int(damage), notes, json.dumps(names), user["id"]))
        except Exception:
            remove_private(names)
            raise HTTPException(409, tr("Bu dalolatnoma allaqachon to'ldirilgan"))
        other = b["owner_id"] if user["id"] == b["renter_id"] else b["renter_id"]
        notify(db, other, "handover_" + kind, f"/handover.html?booking={bid}", mode="owner" if other == b["owner_id"] else "renter",
               actor_id=user["id"], car=car_title(b))
        audit(db, request, "handover_" + kind, "booking", bid, odo=odo, fuel=fuel, damage=damage)
        return ok(_handovers(db, b), 201)


class HandoverConfirmIn(Base):
    agree: bool
    objection: str | None = Field(default=None, max_length=1000)


@require("user")
async def confirm_handover(request: Request):
    bid, kind = path_int(request), request.path_params["kind"]
    if kind not in ("pickup", "return"):
        raise HTTPException(404, tr("Dalolatnoma topilmadi"))
    data = await parse_body(request, HandoverConfirmIn)
    user = request.state.user
    with get_db() as db, transaction(db):
        b = _booking_for(db, bid, user)
        h = one(db.execute("SELECT * FROM handovers WHERE booking_id = ? AND kind = ?", (bid, kind)))
        if not h:
            raise HTTPException(404, tr("Dalolatnoma topilmadi"))
        if h["created_by"] == user["id"] or user["id"] not in (b["renter_id"], b["owner_id"]):
            raise HTTPException(403, tr("Dalolatnomani ikkinchi tomon tasdiqlaydi"))
        if h["confirmed_at"]:
            raise HTTPException(409, tr("Dalolatnoma allaqachon tasdiqlangan"))
        if not data.agree and len((data.objection or "").strip()) < 5:
            raise HTTPException(400, tr("E'tirozingizni yozing (kamida 5 belgi)"))
        db.execute("UPDATE handovers SET confirmed_by = ?, confirmed_at = datetime('now'), objection = ? WHERE id = ?",
                   (user["id"], None if data.agree else data.objection.strip(), h["id"]))
        notify(db, h["created_by"], "handover_confirmed" if data.agree else "handover_objection", f"/handover.html?booking={bid}",
               mode="owner" if h["created_by"] == b["owner_id"] else "renter", actor_id=user["id"], car=car_title(b))
        audit(db, request, "handover_confirmed" if data.agree else "handover_objection", "booking", bid, kind=kind)
        return ok(_handovers(db, b))


routes = [
    Route("/api/bookings/{id:int}/contract", booking_contract, methods=["GET"]),
    Route("/api/contracts/{id:int}/sign/start", contract_sign_start, methods=["POST"]),
    Route("/api/contracts/{id:int}/sign", contract_sign, methods=["POST"]),
    Route("/api/contracts/verify", verify_contract, methods=["GET"]),
    Route("/api/admin/contracts", admin_contracts, methods=["GET"]),
    Route("/api/admin/contracts/{id:int}/approve", admin_approve_contract, methods=["POST"]),
    Route("/api/admin/contract-template", contract_template, methods=["GET"]),
    Route("/api/admin/contract-template", save_contract_template, methods=["PUT"]),
    Route("/api/bookings/{id:int}/handovers", booking_handovers, methods=["GET"]),
    Route("/api/bookings/{id:int}/handover", create_handover, methods=["POST"]),
    Route("/api/bookings/{id:int}/handover/{kind:str}/confirm", confirm_handover, methods=["POST"]),
]
