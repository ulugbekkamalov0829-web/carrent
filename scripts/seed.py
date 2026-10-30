"""Demo ma'lumotlar bilan bazani to'ldirish (barcha demo e'lonlar "DEMO" deb belgilanadi).

Ishlatish:  python -m scripts.seed           (bo'sh bazaga qo'shadi)
            python -m scripts.seed --reset   (bazani tozalab, qaytadan yaratadi)
"""
import json
import random
import secrets
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.db import get_db, init_db, transaction  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.utils import bps_split  # noqa: E402

DEMO_PASSWORD = "CarRent-2026"

# (ism, email, telefon, rol, hudud, til)
USERS = [
    ("Administrator", "admin@carrent.uz", "+998901000000", "admin", "Toshkent", "uz"),
    ("Jasur Karimov", "jasur@carrent.uz", "+998901112233", "user", "Toshkent", "uz"),     # owner + ijarachi
    ("Nodira Rahimova", "nodira@carrent.uz", "+998935556677", "user", "Samarqand", "ru"),
    ("Sardor Toshmatov", "sardor@carrent.uz", "+998977778899", "user", "Farg'ona", "uz"),
    ("Aziz Yusupov", "aziz@carrent.uz", "+998903334455", "user", "Toshkent", "uz"),
    ("Malika Ergasheva", "malika@carrent.uz", "+998946667788", "user", "Toshkent", "en"),
    ("Bekzod Olimov", "bekzod@carrent.uz", "+998999990011", "user", "Samarqand", "uz"),
]

# (egasi, marka, model, yil, rang, kuzov, o'rin, uzatma, yoqilg'i, dvigatel, probeg, yuritma, qulayliklar, shahar,
#  narx, depozit, min, max, km limit, yetkazish, tavsif, suratlar)
# Har bir demo e'londa haqiqiy avtomobil surati bor (static/img/demo).
F_BASE = ["ac", "bluetooth", "usb", "abs", "airbags"]
CARS = [
    (1, "Toyota", "Camry", 2021, "Kumush", "sedan", 5, "automatic", "petrol", 2.5, 74000, "fwd",
     F_BASE + ["camera", "leather", "heated_seats", "cruise", "parking_sensors"], "Toshkent", 900_000, 2_000_000, 1, 30, 300, 100_000,
     "Biznes klass sedan. Teri salon, orqa kamera, adaptiv kruiz. Haydovchi bilan ham berish mumkin (alohida kelishiladi).",
     ["camry.jpg"]),
    (1, "Chevrolet", "Malibu", 2022, "Qora", "sedan", 5, "automatic", "petrol", 2.0, 52000, "fwd",
     F_BASE + ["camera", "parking_sensors", "cruise", "leather", "heated_seats"], "Toshkent", 650_000, 1_500_000, 1, 14, 250, 80_000,
     "Uchrashuvlar va to'ylar uchun. Salon toza, chekilmagan. Aeroportga yetkazib beraman.", ["malibu_black.jpg"]),
    (2, "Kia", "K5", 2023, "Oq", "sedan", 5, "automatic", "petrol", 2.0, 30000, "fwd",
     F_BASE + ["camera", "carplay", "parking_sensors", "navigation"], "Samarqand", 700_000, 1_000_000, 1, 30, 300, 70_000,
     "Yangi model, salon ideal holatda. Navigatsiya, CarPlay. Turistlar uchun Samarqand bo'ylab qulay.", ["k5.jpg"]),
    (2, "Hyundai", "Sonata", 2022, "Kumush", "sedan", 5, "automatic", "petrol", 2.5, 61000, "fwd",
     F_BASE + ["camera", "cruise"], "Samarqand", 600_000, 1_000_000, 1, 30, 400, 60_000,
     "Uzoq safarlar uchun juda qulay va jim. Bagaj katta.", ["sonata.jpg"]),
    (2, "Chevrolet", "Tracker", 2023, "Qizil", "crossover", 5, "automatic", "petrol", 1.2, 27000, "fwd",
     F_BASE + ["camera", "carplay"], "Buxoro", 450_000, 700_000, 1, 30, 300, 50_000,
     "Baland klirens, tejamkor turbo dvigatel. Shahar va shahar tashqarisi uchun.", ["tracker.jpg"]),
    (3, "Chevrolet", "Malibu", 2023, "To'q ko'k", "sedan", 5, "automatic", "petrol", 1.5, 18000, "fwd",
     F_BASE + ["camera", "cruise", "carplay", "parking_sensors"], "Farg'ona", 620_000, 1_000_000, 1, 21, 300, 60_000,
     "Deyarli yangi, turbo dvigatel. Farg'ona vodiysi bo'ylab safar uchun.", ["malibu.jpg"]),
    (3, "Kia", "K5", 2020, "Oq", "sedan", 5, "automatic", "petrol", 2.0, 96000, "fwd", F_BASE + ["camera", "cruise"],
     "Andijon", 480_000, 700_000, 1, 30, 300, None, "Ishonchli, tejamkor sedan. Narxi hamyonbop.", ["k5_white.jpg"]),
]
PHOTO_DIR = Path(__file__).resolve().parent.parent / "static" / "img" / "demo"
# Demo foydalanuvchi va e'lonlar uchun (viloyat, tuman)
USER_PLACES = [("Toshkent shahri", "Yunusobod"), ("Toshkent shahri", "Chilonzor"), ("Samarqand", "Samarqand shahri"),
               ("Farg'ona", "Farg'ona shahri"), ("Toshkent shahri", "Mirzo Ulug'bek"), ("Toshkent shahri", "Yakkasaroy"),
               ("Samarqand", "Urgut")]
CAR_PLACES = {"Toshkent": [("Toshkent shahri", "Chilonzor"), ("Toshkent shahri", "Yunusobod")],
              "Samarqand": [("Samarqand", "Samarqand shahri"), ("Samarqand", "Kattaqo'rg'on shahri")],
              "Buxoro": [("Buxoro", "Buxoro shahri")], "Farg'ona": [("Farg'ona", "Farg'ona shahri")],
              "Andijon": [("Andijon", "Andijon shahri")]}

CAR_COMMENTS = [
    "Avtomobil toza va soz edi, egasi juda xushmuomala.", "Hammasi kelishilgandek bo'ldi, yana ijaraga olaman.",
    "Narxiga arziydi. Konditsioner zo'r ishladi.", "Biroz kechikib topshirildi, lekin umuman yaxshi.",
    "Juda tejamkor ekan, safarimiz a'lo o'tdi!", "Mashina saloni toza, hujjatlari tayyor edi. Rahmat!",
]
RENTER_COMMENTS = ["Avtomobilni vaqtida va toza qaytardi.", "Mas'uliyatli ijarachi, tavsiya qilaman.", "Hammasi kelishilgandek."]


def seed(reset: bool = False) -> None:
    if reset:
        for suffix in ("", "-wal", "-shm"):
            Path(str(settings.DB_PATH) + suffix).unlink(missing_ok=True)
    init_db()
    random.seed(7)
    with get_db() as db:
        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            print("Bazada ma'lumot bor. Qaytadan to'ldirish uchun:  python -m scripts.seed --reset")
            return
        pw = hash_password(DEMO_PASSWORD)
        today = date.today()
        with transaction(db):
            uids = []
            for i, (name, email, phone, role, _region, lang) in enumerate(USERS):
                region, district = USER_PLACES[i]
                created = (today - timedelta(days=200 - i * 20)).isoformat()
                mode = "owner" if i in (1, 2, 3) else "renter"
                uids.append(db.execute(
                    "INSERT INTO users (full_name, email, phone, phone_norm, region, district, password_hash, role, active_mode, lang, "
                    "created_at, email_verified, phone_verified) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (name, email, phone, phone, region, district, pw, role, mode, lang, created, 1, int(i % 2 == 1))).lastrowid)
            cars = []
            for i, c in enumerate(CARS):
                (o, brand, model, year, color, body, seats, tr_, fuel, eng, km, drv, feats, city, price, dep, mn, mx, kml, dlv, desc, photos) = c
                created = (today - timedelta(days=90 - i * 5)).isoformat()
                places = CAR_PLACES[city]
                city, district = places[i % len(places)]
                cid = db.execute(
                    """INSERT INTO cars (owner_id, brand, model, year, color, body_type, seats, transmission, fuel, engine_l,
                       mileage_km, drive, features, city, district, description, price_per_day, deposit, min_days, max_days, km_limit,
                       delivery_price, views, is_demo, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                    (uids[o], brand, model, year, color, body, seats, tr_, fuel, eng, km, drv, json.dumps(sorted(set(feats))),
                     city, district, desc, price, dep, mn, mx, kml, dlv, random.randint(40, 400), created, created)).lastrowid
                cars.append({"id": cid, "price": price, "owner": uids[o], "deposit": dep})
                for pos, fname in enumerate(photos):
                    src = PHOTO_DIR / fname
                    if src.exists():
                        name = secrets.token_hex(16) + ".jpg"
                        shutil.copyfile(src, settings.UPLOAD_DIR / name)
                        db.execute("INSERT INTO car_images (car_id, path, position, label) VALUES (?, ?, ?, 'front')",
                                   (cid, "/uploads/" + name, pos))

            renters = [uids[4], uids[5], uids[6], uids[1], uids[3]]   # Jasur va Sardor ham ijaraga oladi

            def book(car, renter, offset, days, status, created=None):
                s = today + timedelta(days=offset)
                e = s + timedelta(days=days - 1)
                total = days * car["price"]
                commission, payout = bps_split(total, 1000)
                return db.execute(
                    """INSERT INTO bookings (car_id, renter_id, start_date, end_date, days, price_per_day, total_price,
                       commission_bps, commission, owner_payout, deposit, status, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 1000, ?, ?, ?, ?, ?)""",
                    (car["id"], renter, s.isoformat(), e.isoformat(), days, car["price"], total, commission, payout,
                     car["deposit"], status, created or (s - timedelta(days=3)).isoformat())).lastrowid

            for k in range(30):
                car = cars[k % len(cars)]
                renter = renters[k % len(renters)]
                if renter == car["owner"]:
                    renter = renters[(k + 1) % len(renters)]
                start, days = -170 + k * 5, random.randint(1, 4)
                if start + days >= -1:
                    continue
                bid = book(car, renter, start, days, "completed")
                ended = (today + timedelta(days=start + days)).isoformat()
                if k % 4 != 3:
                    db.execute("INSERT INTO reviews (booking_id, car_id, author_id, target_user_id, kind, rating, comment, reply, created_at) "
                               "VALUES (?, ?, ?, ?, 'car', ?, ?, ?, ?)",
                               (bid, car["id"], renter, car["owner"], random.choice([4, 5, 5, 5, 3]), random.choice(CAR_COMMENTS),
                                "Rahmat, yana kutib qolamiz!" if k % 5 == 0 else None, ended))
                if k % 3 == 0:
                    db.execute("INSERT INTO reviews (booking_id, car_id, author_id, target_user_id, kind, rating, comment, created_at) "
                               "VALUES (?, ?, ?, ?, 'renter', ?, ?, ?)",
                               (bid, car["id"], car["owner"], renter, random.choice([4, 5, 5]), random.choice(RENTER_COMMENTS), ended))
            now = date.today().isoformat() + " 00:00:00"
            paid = book(cars[0], uids[4], 3, 3, "approved")          # Aziz: onlayn to'langan (test)
            book(cars[0], uids[5], 10, 2, "approved")                # Malika: to'lov kutilmoqda
            book(cars[2], uids[6], 5, 4, "approved")
            book(cars[4], uids[4], 2, 2, "approved")
            book(cars[3], uids[1], 6, 3, "approved")                 # Jasur ijarachi sifatida (bitta akkaunt)
            book(cars[0], uids[6], 15, 3, "pending", now)
            book(cars[3], uids[5], 13, 3, "pending", now)
            book(cars[5], uids[4], 12, 2, "pending", now)
            book(cars[1], uids[5], 6, 1, "cancelled")
            book(cars[6], uids[4], 7, 2, "rejected")
            total = db.execute("SELECT total_price FROM bookings WHERE id = ?", (paid,)).fetchone()[0]
            db.execute("INSERT INTO payments (booking_id, user_id, provider, amount, status, provider_txn_id, paid_at) "
                       "VALUES (?, ?, 'test', ?, 'paid', ?, datetime('now', '-1 day'))", (paid, uids[4], total, f"test-seed-{paid}"))
            db.execute("UPDATE bookings SET payment_status = 'paid' WHERE id = ?", (paid,))
            # Owner ta'mir uchun yopgan kunlar
            db.execute("INSERT INTO car_blocks (car_id, start_date, end_date, note) VALUES (?, ?, ?, ?)",
                       (cars[1]["id"], (today + timedelta(days=20)).isoformat(), (today + timedelta(days=23)).isoformat(), "Texnik ko'rik"))

            db.execute("INSERT INTO reports (reporter_id, target_type, target_id, reason, comment) VALUES (?, 'car', ?, ?, ?)",
                       (uids[6], cars[6]["id"], "wrong_info", "Probeg e'londagidan ko'proq ko'rinadi."))
            db.execute("INSERT INTO favorites (user_id, car_id) VALUES (?, ?), (?, ?), (?, ?)",
                       (uids[4], cars[1]["id"], uids[4], cars[5]["id"], uids[5], cars[2]["id"]))

            jasur, aziz, malika = uids[1], uids[4], uids[5]
            for s, r, body, read in [
                (aziz, jasur, "Assalomu alaykum! Camry'ni aeroportdan olsam bo'ladimi?", 1),
                (jasur, aziz, "Va alaykum assalom. Ha, bo'ladi, yetkazib berish narxi 50 000 so'm.", 1),
                (aziz, jasur, "Zo'r, rahmat! Unda kelishdik.", 1),
                (malika, jasur, "Hello! Can I take the Malibu for a wedding next week?", 0),
            ]:
                db.execute("INSERT INTO messages (sender_id, receiver_id, car_id, body, is_read) VALUES (?, ?, ?, ?, ?)",
                           (s, r, cars[0]["id"] if "Camry" in body else cars[1]["id"], body, read))
            db.execute("INSERT INTO notifications (user_id, type, params, link) VALUES (?, 'booking_new', ?, ?)",
                       (jasur, json.dumps({"name": "Bekzod Olimov", "car": "Toyota Camry 2021", "start": (today + timedelta(days=15)).isoformat(),
                                           "end": (today + timedelta(days=17)).isoformat(), "days": 3, "total": 2_700_000}, ensure_ascii=False),
                        "/dashboard.html?mode=owner#bookings"))
    print("Demo ma'lumotlar qo'shildi. Barcha demo hisoblar paroli:", DEMO_PASSWORD)
    for name, email, _, role, _, _ in USERS:
        print(f"  {role:<6} {email:<22} {name}")


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
