"""Kurs ishi uchun: sinov akkauntlarini "saytdan haqiqatan foydalanilgandek" ma'lumot bilan to'ldirish (bir martalik).

Har bir rol uchun bittadan to'liq akkaunt:
  * ADMIN   — ADMIN_EMAILS[0] (yo'q bo'lsa admin@carrent.uz): tekshiruv navbatlari to'la (hujjatlar, shartnomalar, nizolar,
              shikoyatlar, to'lov so'rovlari, moderatsiyadagi e'lon, promokodlar, audit jurnali).
  * OWNER   — DEMO_EMAILS[0] (yo'q bo'lsa jasur@carrent.uz): 3–4 e'lon, har xil holatdagi so'rovlar, shartnomalar,
              dalolatnomalar, to'lovlar, daromad va pul yechish, sharhlar, nizo, jarimalar, kalendar, xabarlar.
  * RENTER  — DEMO_EMAILS[1] (yo'q bo'lsa aziz@carrent.uz): bronlar tarixi, onlayn to'lovlar, sevimlilar, sharhlar,
              nizo, jarima, tasdiqlangan hujjatlar, kartalar, xabarlar.
Qarshi tomon sifatida boshqa foydalanuvchilar ishlatiladi (bo'lmasa yaratiladi, ularga kirib bo'lmaydi — tasodifiy parol).
Ishga tushganda bazada 'demo_enriched_v1' belgisi qo'yiladi, qayta to'ldirilmaydi.
"""
import io
import json
import os
import random
import secrets
import shutil
from datetime import date, datetime, timedelta

from app.config import settings
from app.db import get_db, get_setting, one, transaction
from app.security import hash_password

MARK = "demo_enriched_v1"


def _img(text: str, color=(37, 99, 235)) -> bytes:
    """Hujjat/dalolatnoma uchun namunaviy rasm ("NAMUNA" yozuvi bilan) — haqiqiy hujjat emas."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (900, 560), (244, 247, 252))
    d = ImageDraw.Draw(im)
    d.rectangle((20, 20, 880, 540), outline=color, width=6)
    d.rectangle((20, 20, 880, 110), fill=color)
    d.text((50, 50), "CarRent - NAMUNA / SAMPLE", fill=(255, 255, 255))
    d.text((50, 180), text, fill=(20, 30, 60))
    d.text((50, 470), "Kurs ishi uchun namunaviy rasm", fill=(120, 130, 150))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def _private(text: str) -> str:
    name = secrets.token_hex(20) + ".jpg"
    (settings.PRIVATE_DIR / name).write_bytes(_img(text))
    return name


def _uid(db, email: str | None) -> int | None:
    if not email:
        return None
    r = db.execute("SELECT id FROM users WHERE lower(email) = ?", (email.lower(),)).fetchone()
    return r[0] if r else None


def _user(db, email: str, name: str, phone: str, region: str, district: str) -> int:
    uid = _uid(db, email)
    if uid:
        return uid
    return db.execute(
        "INSERT INTO users (full_name, email, phone, phone_norm, region, district, password_hash, role, active_mode, lang, "
        "email_verified, phone_verified, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'user', 'renter', 'uz', 1, 1, ?)",
        (name, email, phone, phone, region, district, hash_password(secrets.token_urlsafe(24)),
         (date.today() - timedelta(days=150)).isoformat())).lastrowid


def _car(db, owner: int, spec: dict) -> int:
    from scripts.seed import PHOTO_DIR
    cid = db.execute(
        """INSERT INTO cars (owner_id, brand, model, year, color, body_type, seats, transmission, fuel, engine_l, mileage_km, drive,
           features, city, district, description, price_per_day, deposit, min_days, max_days, km_limit, delivery_price, plate,
           fuel_policy, tank_l, fuel_price, extra_km_price, require_docs, fuel_per_100, discounts, extras, instant_book,
           is_approved, created_at, lat, lng, address, ownership_status)
           VALUES (?, ?, ?, ?, ?, ?, 5, 'automatic', 'petrol', ?, ?, 'fwd', ?, ?, ?, ?, ?, ?, 1, 30, 300, ?, ?, 'full', 60, 12500, 2000, 1,
                   ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (owner, spec["brand"], spec["model"], spec["year"], spec["color"], spec["body"], spec["engine"], spec["km"],
         json.dumps(spec["features"]), spec["city"], spec["district"], spec["desc"], spec["price"], spec["deposit"], spec["delivery"],
         spec["plate"], spec["per100"], json.dumps(spec["discounts"]), json.dumps(spec["extras"]), int(spec["instant"]),
         int(spec.get("approved", True)), (date.today() - timedelta(days=spec.get("age", 120))).isoformat(),
         spec["lat"], spec["lng"], spec["address"], spec.get("ownership", "verified"))).lastrowid
    src = PHOTO_DIR / spec["photo"]
    if src.exists():
        name = secrets.token_hex(16) + ".jpg"
        shutil.copyfile(src, settings.UPLOAD_DIR / name)
        db.execute("INSERT INTO car_images (car_id, path, position, label) VALUES (?, ?, 0, 'front')", (cid, "/uploads/" + name))
    return cid


FEAT = ["ac", "bluetooth", "usb", "abs", "airbags", "camera", "parking_sensors", "cruise"]
OWNER_CARS = [
    dict(brand="Toyota", model="Camry", year=2021, color="Kumush", body="sedan", engine=2.5, km=74000, features=FEAT + ["leather"],
         city="Toshkent shahri", district="Chilonzor", price=900_000, deposit=2_000_000, delivery=100_000, plate="01A777KA",
         per100=9.5, discounts={"3": 5, "7": 10, "30": 20}, extras={"child_seat": 30000, "cleaning": 60000, "driver": 300000},
         instant=True, photo="camry.jpg", lat=41.285, lng=69.204, address="Chilonzor 9-kvartal, 12-uy oldi",
         desc="Biznes klass sedan. Teri salon, orqa kamera, adaptiv kruiz. Haydovchi bilan ham beriladi."),
    dict(brand="Chevrolet", model="Malibu", year=2022, color="Qora", body="sedan", engine=2.0, km=52000, features=FEAT,
         city="Toshkent shahri", district="Yunusobod", price=650_000, deposit=1_500_000, delivery=80_000, plate="01B245BC",
         per100=8.4, discounts={"7": 8}, extras={"prepaid_fuel": 250000, "cleaning": 50000}, instant=False, photo="malibu_black.jpg",
         lat=41.364, lng=69.288, address="Yunusobod 4-mavze, Amir Temur ko'chasi", desc="Uchrashuv va to'ylar uchun. Aeroportga yetkazib beraman."),
    dict(brand="Chevrolet", model="Tracker", year=2023, color="Qizil", body="crossover", engine=1.2, km=27000, features=FEAT,
         city="Toshkent shahri", district="Mirzo Ulug'bek", price=450_000, deposit=700_000, delivery=50_000, plate="01C318MB",
         per100=7.1, discounts={"3": 5, "7": 10}, extras={"child_seat": 25000, "unlimited_km": 40000}, instant=True, photo="tracker.jpg",
         lat=41.326, lng=69.334, address="Mirzo Ulug'bek, Buyuk Ipak yo'li 21", desc="Baland klirens, tejamkor turbo dvigatel."),
]
PENDING_CAR = dict(brand="Hyundai", model="Sonata", year=2022, color="Kumush", body="sedan", engine=2.5, km=61000, features=FEAT,
                   city="Toshkent shahri", district="Yakkasaroy", price=600_000, deposit=1_000_000, delivery=None, plate="01D512AA",
                   per100=9.0, discounts={}, extras={}, instant=False, photo="sonata.jpg", lat=41.29, lng=69.26,
                   address="Yakkasaroy, Shota Rustaveli 40", desc="Yangi e'lon — admin tekshiruvida.", approved=False,
                   ownership="pending", age=1)
OTHER_CAR = dict(brand="Kia", model="K5", year=2023, color="Oq", body="sedan", engine=2.0, km=30000, features=FEAT + ["carplay"],
                 city="Samarqand", district="Samarqand shahri", price=700_000, deposit=1_000_000, delivery=70_000, plate="30A123KA",
                 per100=8.0, discounts={"7": 10}, extras={"prepaid_fuel": 250000}, instant=False, photo="k5.jpg",
                 lat=39.654, lng=66.96, address="Samarqand, Registon ko'chasi 5", desc="Turistlar uchun qulay.")


def enrich(force: bool = False) -> bool:
    from app.market import plans
    from app.routes.bookings import quote
    from app.routes.rental import ensure_contract
    admins = [e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()]
    demos = [e.strip().lower() for e in os.getenv("DEMO_EMAILS", "").split(",") if e.strip() and e.strip().lower() not in admins[:1]]
    random.seed(2027)
    with get_db() as db:
        if not force and get_setting(db, MARK, ""):
            return False
        A = _uid(db, admins[0] if admins else None) or _uid(db, "admin@carrent.uz")
        O = _uid(db, demos[0] if demos else None) or _uid(db, "jasur@carrent.uz")
        R = _uid(db, demos[1] if len(demos) > 1 else None) or _uid(db, "aziz@carrent.uz")
        if not (A and O and R):
            return False
        today = date.today()
        D = lambda n: (today + timedelta(days=n)).isoformat()                       # noqa: E731
        T = lambda n, h=10: (datetime.combine(today + timedelta(days=n), datetime.min.time()) + timedelta(hours=h)).strftime("%Y-%m-%d %H:%M:%S")  # noqa: E731
        with transaction(db, immediate=True):
            # ---------- qarshi tomonlar ----------
            N = _uid(db, demos[2] if len(demos) > 2 else None) or _user(db, "nodira@carrent.uz", "Nodira Rahimova", "+998935556677", "Samarqand", "Samarqand shahri")
            S = _user(db, "sardor@carrent.uz", "Sardor Toshmatov", "+998977778899", "Farg'ona", "Farg'ona shahri")
            M = _user(db, "malika@carrent.uz", "Malika Ergasheva", "+998946667788", "Toshkent shahri", "Yakkasaroy")
            B = _user(db, "bekzod@carrent.uz", "Bekzod Olimov", "+998999990011", "Samarqand", "Urgut")
            K = _user(db, "kamola@carrent.uz", "Kamola Sobirova", "+998913332211", "Toshkent shahri", "Shayxontohur")

            # ---------- profillar: telefon, hudud, shaxs (niqoblangan), kartalar, hujjatlar ----------
            for uid, name, ph, reg, dist in ((O, None, "+998901112233", "Toshkent shahri", "Chilonzor"),
                                             (R, None, "+998903334455", "Toshkent shahri", "Mirzo Ulug'bek")):
                db.execute("UPDATE users SET phone = COALESCE(NULLIF(phone, ''), ?), phone_norm = COALESCE(phone_norm, ?), region = COALESCE(region, ?), "
                           "district = COALESCE(district, ?), phone_verified = 1, email_verified = 1, identity_status = 'checked', "
                           "pinfl_mask = '3**********012', birth_date = ?, gender = 'm', passport_mask = 'AD *****21' WHERE id = ?",
                           (ph, ph, reg, dist, "1995-04-12" if uid == O else "1998-09-03", uid))
            db.execute("UPDATE users SET active_mode = 'owner' WHERE id = ?", (O,))
            for uid, cards in ((R, [("uzcard", "860049", "4417", 9, 2028, 1), ("humo", "986012", "0391", 3, 2029, 0)]),
                               (O, [("visa", "418783", "7720", 11, 2027, 1)])):
                for brand, f6, l4, em, ey, dflt in cards:
                    db.execute("INSERT OR IGNORE INTO user_cards (user_id, brand, first6, last4, exp_month, exp_year, holder, is_default) "
                               "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (uid, brand, f6, l4, em, ey, "CARD HOLDER", dflt))
            for uid in (O, R, N):
                if not db.execute("SELECT 1 FROM user_documents WHERE user_id = ? AND status = 'approved'", (uid,)).fetchone():
                    db.execute("INSERT INTO user_documents (user_id, kind, files, number_mask, categories, expires_on, status, reviewed_by, reviewed_at, created_at) "
                               "VALUES (?, 'license', ?, 'AF ***4567', 'B, C', ?, 'approved', ?, ?, ?)",
                               (uid, json.dumps([_private("Haydovchilik guvohnomasi")]), D(900), A, T(-60), T(-61)))
                    db.execute("INSERT INTO user_documents (user_id, kind, files, number_mask, status, reviewed_by, reviewed_at, created_at) "
                               "VALUES (?, 'id_card', ?, 'AD ***7721', 'approved', ?, ?, ?)",
                               (uid, json.dumps([_private("ID karta (pasport)")]), A, T(-60), T(-61)))
            # Admin navbati uchun: tekshirilmagan hujjatlar (Sardor, Kamola) va rad etilgan (Bekzod)
            for uid in (S, K):
                db.execute("INSERT INTO user_documents (user_id, kind, files, number_mask, categories, expires_on, status, created_at) "
                           "VALUES (?, 'license', ?, 'AB ***9911', 'B', ?, 'pending', ?)", (uid, json.dumps([_private("Guvohnoma")]), D(700), T(-1, 9)))
                db.execute("INSERT INTO user_documents (user_id, kind, files, number_mask, status, created_at) VALUES (?, 'id_card', ?, 'AC ***1188', 'pending', ?)",
                           (uid, json.dumps([_private("ID karta")]), T(-1, 9)))
            db.execute("INSERT INTO user_documents (user_id, kind, files, number_mask, status, reject_reason, reviewed_by, reviewed_at, created_at) "
                       "VALUES (?, 'license', ?, 'AA ***0001', 'rejected', 'Rasm xira, raqamlar o''qilmaydi. Qayta yuklang.', ?, ?, ?)",
                       (B, json.dumps([_private("Xira rasm")]), A, T(-4), T(-5)))

            # ---------- owner e'lonlari ----------
            own = [r[0] for r in db.execute("SELECT id FROM cars WHERE owner_id = ? ORDER BY id", (O,))]
            if len(own) < 3:
                for spec in OWNER_CARS[len(own):3]:
                    own.append(_car(db, O, spec))
            for cid, spec in zip(own, OWNER_CARS):
                db.execute("UPDATE cars SET extras = ?, instant_book = ?, discounts = ?, ownership_status = 'verified', "
                           "lat = COALESCE(lat, ?), lng = COALESCE(lng, ?), address = COALESCE(address, ?), views = views + ? WHERE id = ?",
                           (json.dumps(spec["extras"]), int(spec["instant"]), json.dumps(spec["discounts"]), spec["lat"], spec["lng"],
                            spec["address"], random.randint(120, 600), cid))
            pending_car = _car(db, O, PENDING_CAR)            # admin moderatsiyasi navbatida
            other = [r[0] for r in db.execute("SELECT id FROM cars WHERE owner_id IN (?, ?) AND is_approved = 1 ORDER BY id", (N, S))]
            if len(other) < 2:
                other.append(_car(db, N, OTHER_CAR))
                other.append(_car(db, N, {**OWNER_CARS[1], "plate": "30B777BC", "city": "Samarqand", "district": "Samarqand shahri",
                                          "lat": 39.65, "lng": 66.95, "address": "Samarqand, Universitet xiyoboni 3", "photo": "malibu.jpg"}))
            db.execute("INSERT INTO car_blocks (car_id, start_date, end_date, note) VALUES (?, ?, ?, 'Texnik ko''rik va moy almashtirish')",
                       (own[1], D(24), D(26)))

            P = plans(db)
            car_row = lambda cid: one(db.execute("SELECT * FROM cars WHERE id = ?", (cid,)))  # noqa: E731

            def book(cid, renter, start, days, status, *, extras=(), plan="none", delivery=False, promo=None, created=None, note=None,
                     responded=True, instant=False):
                car = car_row(cid)
                q = quote(car, days, delivery and car["delivery_price"] is not None, 1000, extras=list(extras), protection=plan, plans=P, promo=promo)
                s, e = D(start), D(start + days - 1)
                cr = created or T(start - 4, 11)
                bid = db.execute(
                    """INSERT INTO bookings (car_id, renter_id, start_date, end_date, days, price_per_day, delivery, total_price, commission_bps,
                       commission, owner_payout, deposit, status, note, extras, extras_total, protection, protection_fee, liability_cap,
                       promo_code, promo_discount, instant, responded_at, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1000, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (cid, renter, s, e, days, q["price_per_day"], q["delivery"], q["total"], q["commission"], q["owner_payout"], q["deposit"],
                     status, note, json.dumps(q["extras"]), q["extras_total"], q["protection"], q["protection_fee"], q["liability_cap"],
                     q["promo_code"], q["promo_discount"], int(instant),
                     (cr if instant else T(start - 4, 13)) if responded and status != "pending" else None, cr, cr)).lastrowid
                return bid

            def contract(bid, stage):
                """stage: pending | owner | signed | approved"""
                c = ensure_contract(db, bid)
                b = one(db.execute("SELECT start_date, created_at FROM bookings WHERE id = ?", (bid,)))
                t0 = b["created_at"]
                if stage in ("owner", "signed", "approved"):
                    db.execute("UPDATE contracts SET owner_signed_at = datetime(?, '+3 hours') WHERE id = ?", (t0, c["id"]))
                if stage in ("signed", "approved"):
                    db.execute("UPDATE contracts SET renter_signed_at = datetime(?, '+5 hours'), status = 'signed' WHERE id = ?", (t0, c["id"]))
                if stage == "approved":
                    db.execute("UPDATE contracts SET status = 'approved', approved_by = ?, approved_at = datetime(?, '+20 hours') WHERE id = ?",
                               (A, t0, c["id"]))

            def handover(bid, kind, km, fuel, by, confirm_by, day, damage=0, notes=None, objection=None):
                db.execute("INSERT INTO handovers (booking_id, kind, odometer_km, fuel_pct, clean, damage, notes, photos, created_by, created_at, "
                           "confirmed_by, confirmed_at, objection, docs_checked) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
                           (bid, kind, km, fuel, damage, notes, json.dumps([_private(f"Dalolatnoma rasmi: {kind}")]), by, T(day, 9),
                            confirm_by, T(day, 10) if confirm_by else None, objection))

            def pay(bid, user, provider="test", day=-1):
                amt = db.execute("SELECT total_price FROM bookings WHERE id = ?", (bid,)).fetchone()[0]
                db.execute("INSERT INTO payments (booking_id, user_id, provider, amount, status, provider_txn_id, paid_at, created_at) "
                           "VALUES (?, ?, ?, ?, 'paid', ?, ?, ?)", (bid, user, provider, amt, f"demo-{bid}-{secrets.token_hex(4)}", T(day, 12), T(day, 12)))
                db.execute("UPDATE bookings SET payment_status = 'paid' WHERE id = ?", (bid,))

            def review(bid, cid, author, target, kind, rating, comment, reply=None, day=0):
                db.execute("INSERT INTO reviews (booking_id, car_id, author_id, target_user_id, kind, rating, comment, reply, created_at) "
                           "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (bid, cid, author, target, kind, rating, comment, reply, T(day, 18)))

            # promokodlar
            for code, pct, amt, mx, exp, note in (("BAHOR2027", 50, 0, 200, D(120), "Bahorgi aksiya (Instagram)"),
                                                  ("BIRINCHI", 0, 50000, None, None, "Birinchi bron uchun"),
                                                  ("YOZ2026", 10, 0, 100, D(-30), "Yozgi aksiya — tugagan")):
                db.execute("INSERT OR IGNORE INTO promo_codes (code, pct, amount, max_uses, expires_on, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (code, pct, amt, mx, exp, note, T(-40)))
            promo1 = one(db.execute("SELECT * FROM promo_codes WHERE code = 'BIRINCHI'"))

            camry, malibu, tracker = own[0], own[1], own[2]
            # ============ OWNER e'lonlari bo'yicha bronlar ============
            # 1) R — yakunlangan, to'liq jarayon: shartnoma, dalolatnoma, onlayn to'lov, sharhlar, jarima (to'langan)
            b1 = book(camry, R, -40, 3, "completed", extras=["child_seat"], plan="standard", delivery=True, promo=promo1,
                      note="Aeroportdan olib ketaman, soat 9:00 da")
            contract(b1, "approved"); pay(b1, R, "click", -44)
            handover(b1, "pickup", 74120, 100, O, R, -40, notes="Mashina toza, bak to'la")
            handover(b1, "return", 74890, 95, R, O, -38, notes="Vaqtida qaytarildi")
            review(b1, camry, R, O, "car", 5, "Mashina toza va soz edi, egasi juda xushmuomala. Aeroportga o'z vaqtida olib keldi.",
                   "Rahmat, Aziz! Yana kutib qolamiz.", -37)
            review(b1, camry, O, R, "renter", 5, "Avtomobilni vaqtida va toza qaytardi. Tavsiya qilaman.", day=-37)
            db.execute("INSERT INTO fines (booking_id, owner_id, renter_id, happened_at, amount, protocol, description, status, paid_at, created_at) "
                       "VALUES (?, ?, ?, ?, 375000, 'RR7012345', 'Tezlikni oshirish (radar), Amir Temur shoh ko''chasi', 'paid', ?, ?)",
                       (b1, O, R, T(-39, 15)[:16], T(-30), T(-33)))
            # 2) M — yakunlangan, shikast bo'yicha nizo hal qilingan (kelishuv)
            b2 = book(malibu, M, -28, 4, "completed", plan="none")
            contract(b2, "approved")
            handover(b2, "pickup", 52300, 80, O, M, -28)
            handover(b2, "return", 53100, 60, M, O, -25, damage=1, notes="Orqa bamperda yangi chiziq", objection="Chiziq avvaldan bor edi")
            db.execute("INSERT INTO disputes (booking_id, opened_by, against_id, type, description, amount, status, response, response_at, outcome, "
                       "decision_note, compensation, resolved_by, resolved_at, created_at) VALUES (?, ?, ?, 'damage', ?, 600000, 'resolved', ?, ?, "
                       "'split', ?, 300000, ?, ?, ?)",
                       (b2, O, M, "Qaytarishda orqa bamperda yangi chiziq paydo bo'ldi, dalolatnomada rasm bor. Bo'yash 600 000 so'm.",
                        "Chiziq kichik, olishda ham bo'lgan bo'lishi mumkin.", T(-23), "Olish dalolatnomasidagi rasmda bu joy ko'rinmaydi. "
                        "Xarajat teng bo'linadi.", A, T(-20), T(-24)))
            review(b2, malibu, M, O, "car", 4, "Mashina yaxshi, lekin bamper masalasida kelishmovchilik bo'ldi.", day=-24)
            # 3) B — yakunlangan, ochiq jarima (e'tiroz bildirilgan)
            b3 = book(tracker, B, -18, 2, "completed")
            contract(b3, "approved")
            handover(b3, "pickup", 27050, 100, O, B, -18); handover(b3, "return", 27460, 100, B, O, -17)
            db.execute("INSERT INTO fines (booking_id, owner_id, renter_id, happened_at, amount, protocol, description, status, created_at) "
                       "VALUES (?, ?, ?, ?, 250000, 'RR7098811', 'Qizil chiroqqa o''tish (kamera)', 'disputed', ?)", (b3, O, B, T(-18, 19)[:16], T(-6)))
            review(b3, tracker, B, O, "car", 5, "Juda tejamkor ekan, safarimiz a'lo o'tdi!", day=-16)
            # 4) R — hozir davom etayotgan ijara: ikkala tomon imzolagan, admin tasdig'ini kutmoqda; olish dalolatnomasi bor
            b4 = book(tracker, R, -1, 4, "approved", extras=["child_seat", "unlimited_km"], plan="premium", created=T(-5, 10))
            contract(b4, "signed"); pay(b4, R, "payme", -4)
            handover(b4, "pickup", 27610, 100, O, R, -1, notes="Bolalar o'rindig'i o'rnatildi")
            # 5) K — kelgusi, faqat owner imzolagan (ijarachi imzosi kutilmoqda), joyida to'lov
            b5 = book(camry, K, 8, 3, "approved", plan="standard", created=T(-1, 16))
            contract(b5, "owner")
            # 6) Darhol bron (S hujjatlari tekshiruvda, shuning uchun so'rov) va boshqa kutilayotgan so'rovlar
            book(malibu, S, 12, 2, "pending", created=T(0, 8), note="To'y uchun, gul bilan bezatsak bo'ladimi?")
            book(camry, M, 15, 5, "pending", extras=["driver"], plan="premium", created=T(0, 9))
            b6 = book(tracker, N, 20, 3, "approved", plan="standard", instant=True, created=T(-2, 20))
            contract(b6, "pending")
            # 7) rad etilgan va bekor qilingan
            book(malibu, B, 4, 2, "rejected", created=T(-3, 12), note="Toshkentdan tashqariga chiqaman")
            bc = book(camry, M, 5, 2, "cancelled", created=T(-6, 10))
            # ============ RENTER boshqa owner'lar mashinalarida ============
            o1, o2 = other[0], other[-1]
            owner_of = lambda cid: db.execute("SELECT owner_id FROM cars WHERE id = ?", (cid,)).fetchone()[0]  # noqa: E731
            b7 = book(o1, R, -70, 3, "completed", plan="standard")
            contract(b7, "approved"); pay(b7, R, "click", -73)
            handover(b7, "pickup", 30100, 100, owner_of(o1), R, -70); handover(b7, "return", 30650, 100, R, owner_of(o1), -68)
            review(b7, o1, R, owner_of(o1), "car", 5, "Samarqand bo'ylab safar uchun juda qulay bo'ldi. Rahmat!", "Xush kelibsiz!", -67)
            review(b7, o1, owner_of(o1), R, "renter", 5, "Mas'uliyatli ijarachi, tavsiya qilaman.", day=-67)
            # Nizo: depozit qaytarilmagan — admin ko'rib chiqmoqda
            b8 = book(o2, R, -12, 2, "completed")
            contract(b8, "approved")
            handover(b8, "pickup", 40100, 70, owner_of(o2), R, -12); handover(b8, "return", 40420, 70, R, owner_of(o2), -11)
            db.execute("INSERT INTO disputes (booking_id, opened_by, against_id, type, description, amount, status, response, response_at, created_at) "
                       "VALUES (?, ?, ?, 'deposit', ?, 1000000, 'in_review', ?, ?, ?)",
                       (b8, R, owner_of(o2), "Mashinani shikastsiz va to'la bak bilan qaytardim, dalolatnomada tasdiqlangan, lekin depozit 10 kundan beri qaytarilmadi.",
                        "Salonni tozalash kerak bo'ldi, 150 000 so'm ushlab qolaman.", T(-8), T(-9)))
            db.execute("INSERT INTO fines (booking_id, owner_id, renter_id, happened_at, amount, protocol, description, status, created_at) "
                       "VALUES (?, ?, ?, ?, 375000, 'RR7123400', 'Tezlikni oshirish, M39 yo''li', 'open', ?)", (b8, owner_of(o2), R, T(-12, 16)[:16], T(-2)))
            b9 = book(o1, R, 25, 4, "approved", extras=["prepaid_fuel"], plan="premium", created=T(-1, 21))
            contract(b9, "signed"); pay(b9, R, "click", -1)
            book(o2, R, 40, 3, "pending", created=T(0, 7))
            bcr = book(o2, R, 9, 2, "cancelled", created=T(-7, 10))
            pay(bcr, R, "payme", -7)
            db.execute("UPDATE payments SET status = 'refunded', refund_amount = amount, cancelled_at = ? WHERE booking_id = ?", (T(-5), bcr))
            db.execute("UPDATE bookings SET payment_status = 'refunded' WHERE id = ?", (bcr,))
            book(o1, R, -55, 2, "rejected", created=T(-58))
            # O ham ijarachi sifatida (bitta akkaunt — ikki rol)
            b10 = book(o1, O, -90, 2, "completed")
            contract(b10, "approved")
            review(b10, o1, O, owner_of(o1), "car", 4, "Yaxshi mashina, biroz kech topshirildi.", day=-87)

            # ---------- pul: owner'ga to'lov, pul yechish so'rovlari ----------
            pid = db.execute("INSERT INTO payouts (owner_id, amount, note, created_by, created_at) VALUES (?, ?, 'Click hamyonga o''tkazildi', ?, ?)",
                             (O, 2_000_000, A, T(-30))).lastrowid
            db.execute("INSERT INTO payout_requests (owner_id, amount, method, card_last4, note, status, payout_id, processed_by, processed_at, created_at) "
                       "VALUES (?, 2000000, 'card', '7720', NULL, 'paid', ?, ?, ?, ?)", (O, pid, A, T(-30), T(-31)))
            db.execute("INSERT INTO payout_requests (owner_id, amount, method, card_last4, note, status, created_at) "
                       "VALUES (?, 1500000, 'card', '7720', 'Iltimos, dushanbagacha', 'pending', ?)", (O, T(-1, 18)))

            # ---------- sevimlilar, shikoyatlar, xabarlar, bildirishnomalar ----------
            for cid in (o1, o2, camry):
                db.execute("INSERT OR IGNORE INTO favorites (user_id, car_id) VALUES (?, ?)", (R, cid))
            db.execute("INSERT INTO reports (reporter_id, target_type, target_id, reason, comment, created_at) VALUES (?, 'car', ?, 'wrong_info', ?, ?)",
                       (B, o2, "E'londa 2023 yil deyilgan, texpasportda 2021.", T(-2)))
            db.execute("INSERT INTO reports (reporter_id, target_type, target_id, reason, comment, status, resolved_by, resolved_at, created_at) "
                       "VALUES (?, 'user', ?, 'abuse', 'Chatda qo''pol gapirdi.', 'resolved', ?, ?, ?)", (O, B, A, T(-10), T(-12)))
            chat = [
                (R, O, camry, "Assalomu alaykum! Camry'ni aeroportdan olsam bo'ladimi? Reys ertalab 8:30 da.", -45, 1),
                (O, R, camry, "Va alaykum assalom. Ha, yetkazib berish 100 000 so'm, 9:00 da terminal oldida bo'laman.", -45, 1),
                (R, O, camry, "Zo'r, bolalar o'rindig'i ham kerak bo'ladi.", -45, 1),
                (O, R, camry, "Bron qilishda \"Qo'shimcha xizmatlar\"dan belgilang, o'rnatib qo'yaman.", -45, 1),
                (R, O, tracker, "Ertaga soat nechada mashinani olsam bo'ladi?", -2, 1),
                (O, R, tracker, "10:00 da Buyuk Ipak yo'li 21 da kutaman. Hujjatlaringizni olib keling.", -2, 1),
                (R, O, tracker, "Rahmat, yetib keldim, mashina zo'r!", -1, 0),
                (M, O, camry, "Hello! Can I take the Camry with a driver for 5 days?", 0, 0),
                (S, O, malibu, "Assalomu alaykum, to'y uchun mashinani gul bilan bezatsak bo'ladimi?", 0, 0),
                (R, owner_of(o2), o2, "Depozitni qachon qaytarasiz? Dalolatnomada hammasi joyida deb yozilgan.", -9, 1),
                (owner_of(o2), R, o2, "Salonni tozalashga 150 000 ketdi, qolganini o'tkazaman.", -8, 1),
            ]
            for s_, r_, cid, body, day, read in chat:
                db.execute("INSERT INTO messages (sender_id, receiver_id, car_id, body, is_read, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                           (s_, r_, cid, body, read, T(day, random.randint(9, 20))))
            notif = [
                (O, "booking_new", {"name": "Sardor Toshmatov", "car": "Chevrolet Malibu 2022", "start": D(12), "end": D(13), "days": 2, "total": 1_430_000}, "/dashboard.html?mode=owner#bookings", "owner"),
                (O, "booking_instant", {"name": "Nodira Rahimova", "car": "Chevrolet Tracker 2023", "start": D(20), "end": D(22), "days": 3, "total": 1_485_000}, "/dashboard.html?mode=owner#bookings", "owner"),
                (O, "fine_disputed", {"car": "Chevrolet Tracker 2023"}, "/dashboard.html?mode=owner#fines", "owner"),
                (R, "booking_approved", {"car": "Kia K5 2023", "start": D(25), "end": D(28)}, "/dashboard.html?mode=renter#bookings", "renter"),
                (R, "fine_new", {"car": "Kia K5 2023", "amount": 375000, "at": T(-12, 16)[:16]}, "/dashboard.html?mode=renter#fines", "renter"),
            ]
            for uid, typ, params, link, mode in notif:
                db.execute("INSERT INTO notifications (user_id, type, params, link, mode, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                           (uid, typ, json.dumps(params, ensure_ascii=False), link, mode, T(0, random.randint(6, 9))))

            # ---------- admin: eslatmalar va jurnal ----------
            db.execute("INSERT INTO admin_notes (user_id, author_id, kind, body, created_at) VALUES (?, ?, 'warning', ?, ?)",
                       (B, A, "Chatda qo'pollik bo'yicha ogohlantirildi (shikoyat #resolved).", T(-10)))
            db.execute("INSERT INTO admin_notes (user_id, author_id, kind, body, created_at) VALUES (?, ?, 'note', ?, ?)",
                       (O, A, "Ishonchli owner: hujjatlar to'liq, javob tezligi yuqori.", T(-20)))
            for action, ttype, tid, det, day in (("doc_review", "user", R, {"approve": True}, -60), ("car_approved", "car", camry, {}, -100),
                                                 ("dispute_resolved", "dispute", None, {"outcome": "split"}, -20),
                                                 ("payout_paid", "user", O, {"amount": 2000000}, -30), ("promo_created", "promo", None, {"code": "BAHOR2027"}, -40),
                                                 ("settings_changed", "settings", None, {"commission_percent": 10}, -50)):
                db.execute("INSERT INTO audit_logs (actor_id, action, target_type, target_id, details, ip, created_at) VALUES (?, ?, ?, ?, ?, '127.0.0.1', ?)",
                           (A, action, ttype, tid, json.dumps(det), T(day, 15)))
            # Avvalgi (seed) bronlarga ham shartnoma: yakunlanganlari tasdiqlangan, kelgusilari imzolangan
            for bid, st in db.execute("""SELECT b.id, b.status FROM bookings b JOIN cars c ON c.id = b.car_id
                                         WHERE b.status IN ('approved', 'completed') AND (b.renter_id IN (?, ?) OR c.owner_id IN (?, ?))
                                         AND NOT EXISTS (SELECT 1 FROM contracts k WHERE k.booking_id = b.id)""", (O, R, O, R)).fetchall():
                contract(bid, "approved" if st == "completed" else "signed")
            db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, datetime('now'))", (MARK,))
        return True


if __name__ == "__main__":
    import sys
    from app.db import init_db
    init_db()
    print("To'ldirildi" if enrich(force="--force" in sys.argv) else "O'tkazib yuborildi (allaqachon to'ldirilgan yoki akkauntlar yo'q)")
