"""Avtomobil e'lonlari: CRUD, qidiruv va filtrlash, rasmlar, kalendar, sevimlilar."""
import json
import secrets
from datetime import timedelta

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.routing import Route

from ..config import settings
from ..db import get_db, one, rows, transaction
from ..i18n import tr
from ..schemas import CarIn
from ..security import current_user_or_none, require
from ..utils import audit, complete_finished_bookings, ok, parse_body, path_int, q_date, q_int, q_str, today

CAR_COLUMNS = """
    c.id, c.owner_id, c.brand, c.model, c.year, c.color, c.body_type, c.seats, c.transmission, c.fuel, c.engine_l,
    c.mileage_km, c.drive, c.features, c.city, c.description, c.price_per_day, c.deposit, c.min_days, c.max_days,
    c.km_limit, c.delivery_price, c.is_active, c.is_approved, c.views, c.is_demo, c.created_at, c.updated_at,
    (SELECT path FROM car_images i WHERE i.car_id = c.id ORDER BY position, id LIMIT 1) AS cover,
    (SELECT ROUND(AVG(rating), 1) FROM reviews r WHERE r.car_id = c.id AND r.kind = 'car') AS rating,
    (SELECT COUNT(*) FROM reviews r WHERE r.car_id = c.id AND r.kind = 'car') AS reviews_count
"""
FAV_COLUMN = ", EXISTS(SELECT 1 FROM favorites f WHERE f.car_id = c.id AND f.user_id = ?) AS is_favorite"
PUBLIC_WHERE = "c.is_active = 1 AND c.is_approved = 1 AND u.is_active = 1"

SORTS = {
    "new": "c.created_at DESC, c.id DESC",
    "price_asc": "c.price_per_day ASC, c.id DESC",
    "price_desc": "c.price_per_day DESC, c.id DESC",
    "rating": "rating IS NULL, rating DESC, reviews_count DESC",
    "year": "c.year DESC, c.id DESC",
    "popular": "c.views DESC, c.id DESC",
}
IMAGE_SIGNATURES = [(b"\xff\xd8\xff", ".jpg"), (b"\x89PNG\r\n\x1a\n", ".png")]


def serialize(car: dict) -> dict:
    car["features"] = json.loads(car.get("features") or "[]")
    car["title"] = f"{car['brand']} {car['model']}"
    if "is_favorite" in car:
        car["is_favorite"] = bool(car["is_favorite"])
    return car


IMAGE_LABELS = {"front", "back", "side", "interior", "dashboard", "trunk", "other"}
MAX_SIDE = 1600   # px: katta rasmlar kichraytiriladi (sahifa tez ochilishi uchun)


def reencode_image(content: bytes, max_side: int = MAX_SIDE, square: bool = False) -> bytes:
    """Rasmni Pillow bilan qayta kodlash: zararli qo'shimcha ma'lumot, EXIF va GPS metama'lumotlari tushib qoladi.
    Natija har doim JPEG (sifat 85). Buzilgan yoki rasm bo'lmagan fayl ValueError beradi."""
    import io

    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = 40_000_000          # "decompression bomb" himoyasi
    try:
        with Image.open(io.BytesIO(content)) as im:
            im.verify()
        with Image.open(io.BytesIO(content)) as im:
            im = ImageOps.exif_transpose(im)      # telefondagi burilishni saqlab qolamiz, EXIF'ni esa tashlaymiz
            im = im.convert("RGB")
            if square:   # avatar: markazdan kvadrat qirqiladi
                side = min(im.size)
                im = im.crop(((im.width - side) // 2, (im.height - side) // 2, (im.width + side) // 2, (im.height + side) // 2))
            im.thumbnail((max_side, max_side))
            out = io.BytesIO()
            im.save(out, "JPEG", quality=85, optimize=True)   # exif= berilmaydi -> metama'lumot yozilmaydi
            return out.getvalue()
    except Exception as exc:
        raise ValueError() from exc


def _image_ext(head: bytes) -> str | None:
    for sig, ext in IMAGE_SIGNATURES:
        if head.startswith(sig):
            return ext
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    return None


def get_car_row(db, car_id: int, user_id: int | None = None) -> dict:
    car = one(db.execute(f"SELECT {CAR_COLUMNS}{FAV_COLUMN} FROM cars c WHERE c.id = ?", (user_id or 0, car_id)))
    if not car:
        raise HTTPException(404, tr("E'lon topilmadi"))
    return serialize(car)


def own_car(db, car_id: int, user: dict) -> dict:
    """Egalik tekshiruvi (IDOR himoyasi): boshqa birovning e'loni 403 qaytaradi."""
    car = get_car_row(db, car_id, user["id"])
    if car["owner_id"] != user["id"]:
        raise HTTPException(403, tr("Bu e'lon sizga tegishli emas"))
    return car


def search_where(request: Request) -> tuple[list[str], list]:
    where, params = [PUBLIC_WHERE], []
    if q := q_str(request, "q"):
        where.append("(c.brand || ' ' || c.model LIKE ? OR c.description LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    for field in ("city", "brand", "body_type", "transmission", "fuel"):
        if val := q_str(request, field):
            where.append(f"c.{field} = ? COLLATE NOCASE"); params.append(val)
    for field, col, op in (("min_price", "c.price_per_day", ">="), ("max_price", "c.price_per_day", "<="),
                           ("seats", "c.seats", ">="), ("year_from", "c.year", ">=")):
        if (v := q_int(request, field)) is not None:
            where.append(f"{col} {op} ?"); params.append(v)
    if (v := q_int(request, "rating_min", lo=1, hi=5)) is not None:
        where.append("(SELECT AVG(rating) FROM reviews r WHERE r.car_id = c.id AND r.kind = 'car') >= ?"); params.append(v)
    for feat in (q_str(request, "features", 300) or "").split(","):
        if feat.strip():
            where.append("EXISTS (SELECT 1 FROM json_each(c.features) WHERE value = ?)"); params.append(feat.strip())
    if request.query_params.get("delivery") == "1":
        where.append("c.delivery_price IS NOT NULL")
    start, end = q_date(request, "start"), q_date(request, "end")
    if start and end:
        if end < start:
            raise HTTPException(400, tr("Tugash sanasi boshlanish sanasidan oldin bo'lmasligi kerak"))
        where.append("""NOT EXISTS (SELECT 1 FROM bookings b WHERE b.car_id = c.id AND b.status IN ('approved', 'pending')
                        AND b.start_date <= ? AND b.end_date >= ?)
                        AND NOT EXISTS (SELECT 1 FROM car_blocks k WHERE k.car_id = c.id AND k.start_date <= ? AND k.end_date >= ?)""")
        params += [end.isoformat(), start.isoformat(), end.isoformat(), start.isoformat()]
    return where, params


async def list_cars(request: Request):
    """Server tomonida qidiruv: faqat faol, tasdiqlangan va egasi bloklanmagan e'lonlar."""
    user = current_user_or_none(request)
    where, params = search_where(request)
    sort = SORTS.get(request.query_params.get("sort", "new"), SORTS["new"])
    page = q_int(request, "page", 1, lo=1)
    limit = q_int(request, "limit", 12, lo=1, hi=48)
    w = " AND ".join(where)
    with get_db() as db:
        total = db.execute(f"SELECT COUNT(*) FROM cars c JOIN users u ON u.id = c.owner_id WHERE {w}", params).fetchone()[0]
        items = rows(db.execute(
            f"SELECT {CAR_COLUMNS}{FAV_COLUMN} FROM cars c JOIN users u ON u.id = c.owner_id WHERE {w} "
            f"ORDER BY {sort} LIMIT ? OFFSET ?", [user["id"] if user else 0] + params + [limit, (page - 1) * limit]))
    return ok({"items": [serialize(c) for c in items], "total": total, "page": page, "pages": max(1, -(-total // limit))})


async def meta(request: Request):
    base = "FROM cars WHERE is_active = 1 AND is_approved = 1"
    with get_db() as db:
        cities = [dict(city=r[0], count=r[1]) for r in db.execute(f"SELECT city, COUNT(*) {base} GROUP BY city ORDER BY 2 DESC")]
        brands = [r[0] for r in db.execute(f"SELECT DISTINCT brand {base} ORDER BY brand")]
        lo, hi, total = db.execute(f"SELECT MIN(price_per_day), MAX(price_per_day), COUNT(*) {base}").fetchone()
        owners = db.execute(f"SELECT COUNT(DISTINCT owner_id) {base}").fetchone()[0]
        done = db.execute("SELECT COUNT(*) FROM bookings WHERE status = 'completed'").fetchone()[0]
        bps = int(db.execute("SELECT value FROM settings WHERE key = 'commission_bps'").fetchone()[0])
        support = db.execute("SELECT id FROM users WHERE role = 'admin' AND is_active = 1 ORDER BY id LIMIT 1").fetchone()
    return ok({"cities": cities, "brands": brands, "price_min": lo or 0, "price_max": hi or 0, "cars_total": total,
               "owners_total": owners, "completed_total": done, "commission_bps": bps, "support_user_id": support[0] if support else None,
               "demo": settings.DEMO_MODE, "max_images": settings.MAX_IMAGES_PER_CAR, "max_image_mb": settings.MAX_IMAGE_MB,
               "dev_inbox": settings.DEV_INBOX, "email_real": settings.email_enabled,
               "sms_real": settings.sms_enabled, "payments": {"test": settings.PAYMENT_TEST_MODE, "click": settings.click_enabled,
                                                              "payme": settings.payme_enabled}})


async def get_car(request: Request):
    car_id = path_int(request)
    user = current_user_or_none(request)
    with get_db() as db:
        car = get_car_row(db, car_id, user["id"] if user else None)
        owner = one(db.execute(
            """SELECT u.id, u.full_name, u.phone, u.created_at, u.is_active, u.avatar, u.show_phone, u.phone_verified, u.email_verified,
                      (SELECT COUNT(*) FROM cars WHERE owner_id = u.id) AS cars_count,
                      (SELECT ROUND(AVG(r.rating), 1) FROM reviews r JOIN cars c2 ON c2.id = r.car_id
                        WHERE c2.owner_id = u.id AND r.kind = 'car') AS rating,
                      (SELECT COUNT(*) FROM bookings b JOIN cars c3 ON c3.id = b.car_id
                        WHERE c3.owner_id = u.id AND b.status = 'completed') AS trips
               FROM users u WHERE u.id = ?""", (car["owner_id"],)))
        is_owner = bool(user and user["id"] == car["owner_id"])
        visible = car["is_active"] and car["is_approved"] and owner["is_active"]
        if not visible and not (is_owner or (user and user["role"] == "admin")):
            raise HTTPException(404, tr("E'lon topilmadi"))
        car["images"] = rows(db.execute("SELECT id, path, label FROM car_images WHERE car_id = ? ORDER BY position, id", (car_id,)))
        if not is_owner:
            db.execute("UPDATE cars SET views = views + 1 WHERE id = ?", (car_id,))
        # O'xshash avtomobillar: shu kuzov yoki shu shahar, narxi ±40%
        car["similar"] = [serialize(c) for c in rows(db.execute(
            f"""SELECT {CAR_COLUMNS} FROM cars c JOIN users u ON u.id = c.owner_id
                WHERE {PUBLIC_WHERE} AND c.id != ? AND (c.body_type = ? OR c.city = ?)
                AND c.price_per_day BETWEEN ? AND ?
                ORDER BY (c.body_type = ?) + (c.city = ?) DESC, ABS(c.price_per_day - ?) LIMIT 4""",
            (car_id, car["body_type"], car["city"], int(car["price_per_day"] * 0.6), int(car["price_per_day"] * 1.4),
             car["body_type"], car["city"], car["price_per_day"])))]
    if not user:
        owner["phone"] = None  # telefon faqat tizimga kirganlarga ko'rinadi
    if not owner.pop("show_phone", 1) and not is_owner:
        owner["phone"] = None  # owner sozlamalarda telefonni yashirgan
    owner.pop("is_active", None)
    car["owner"] = owner
    car["is_mine"] = is_owner
    return ok(car)


async def calendar(request: Request):
    car_id = path_int(request)
    start = q_date(request, "from") or today().replace(day=1)
    end = q_date(request, "to") or (start + timedelta(days=92))
    with get_db() as db:
        get_car_row(db, car_id)
        complete_finished_bookings(db)
        ranges = rows(db.execute(
            "SELECT start_date, end_date, status FROM bookings WHERE car_id = ? AND status IN ('approved', 'pending') "
            "AND start_date <= ? AND end_date >= ? ORDER BY start_date", (car_id, end.isoformat(), start.isoformat())))
        ranges += [dict(r, status="blocked") for r in rows(db.execute(
            "SELECT start_date, end_date FROM car_blocks WHERE car_id = ? AND start_date <= ? AND end_date >= ?",
            (car_id, end.isoformat(), start.isoformat())))]
    return ok({"from": start.isoformat(), "to": end.isoformat(), "today": today().isoformat(), "ranges": ranges})


# ---------------- Owner yopib qo'ygan kunlar ----------------
@require("user")
async def list_blocks(request: Request):
    car_id = path_int(request)
    with get_db() as db:
        own_car(db, car_id, request.state.user)
        items = rows(db.execute("SELECT id, start_date, end_date, note FROM car_blocks WHERE car_id = ? AND end_date >= ? "
                                "ORDER BY start_date", (car_id, today().isoformat())))
    return ok({"items": items})


@require("user")
async def add_block(request: Request):
    from ..schemas import BlockIn
    car_id = path_int(request)
    data = await parse_body(request, BlockIn)
    if data.end_date < data.start_date:
        raise HTTPException(400, tr("Tugash sanasi boshlanish sanasidan oldin bo'lmasligi kerak"))
    if data.start_date < today():
        raise HTTPException(400, tr("O'tib ketgan sanani bron qilib bo'lmaydi"))
    s, e = data.start_date.isoformat(), data.end_date.isoformat()
    with get_db() as db:
        with transaction(db, immediate=True):
            own_car(db, car_id, request.state.user)
            if db.execute("SELECT 1 FROM bookings WHERE car_id = ? AND status = 'approved' AND start_date <= ? AND end_date >= ?",
                          (car_id, e, s)).fetchone():
                raise HTTPException(409, tr("Bu sanalarda tasdiqlangan bron bor — ularni yopib bo'lmaydi"))
            cur = db.execute("INSERT INTO car_blocks (car_id, start_date, end_date, note) VALUES (?, ?, ?, ?)", (car_id, s, e, data.note))
    return ok({"id": cur.lastrowid, "start_date": s, "end_date": e, "note": data.note}, 201)


@require("user")
async def delete_block(request: Request):
    car_id, bid = path_int(request), path_int(request, "block_id")
    with get_db() as db:
        own_car(db, car_id, request.state.user)
        db.execute("DELETE FROM car_blocks WHERE id = ? AND car_id = ?", (bid, car_id))
    return ok()


@require("user")
async def reorder_images(request: Request):
    from ..schemas import ImageOrderIn
    car_id = path_int(request)
    data = await parse_body(request, ImageOrderIn)
    with get_db() as db:
        own_car(db, car_id, request.state.user)
        have = [r[0] for r in db.execute("SELECT id FROM car_images WHERE car_id = ?", (car_id,))]
        if sorted(have) != sorted(data.ids):
            raise HTTPException(400, tr("Rasm topilmadi"))
        with transaction(db):
            for pos, i in enumerate(data.ids):
                db.execute("UPDATE car_images SET position = ? WHERE id = ?", (pos, i))
        images = rows(db.execute("SELECT id, path, label FROM car_images WHERE car_id = ? ORDER BY position, id", (car_id,)))
    return ok({"images": images})


@require("user")
async def label_image(request: Request):
    from ..schemas import ImageLabelIn
    car_id, img_id = path_int(request), path_int(request, "img_id")
    data = await parse_body(request, ImageLabelIn)
    with get_db() as db:
        own_car(db, car_id, request.state.user)
        if not db.execute("UPDATE car_images SET label = ? WHERE id = ? AND car_id = ?", (data.label, img_id, car_id)).rowcount:
            raise HTTPException(404, tr("Rasm topilmadi"))
    return ok({"id": img_id, "label": data.label})


async def car_reviews(request: Request):
    car_id = path_int(request)
    with get_db() as db:
        items = rows(db.execute(
            "SELECT r.id, r.rating, r.comment, r.reply, r.created_at, u.full_name AS author "
            "FROM reviews r JOIN users u ON u.id = r.author_id WHERE r.car_id = ? AND r.kind = 'car' ORDER BY r.id DESC LIMIT 50",
            (car_id,)))
    return ok({"items": items})


@require()
async def my_cars(request: Request):
    uid = request.state.user["id"]
    with get_db() as db:
        items = rows(db.execute(
            f"""SELECT {CAR_COLUMNS},
                (SELECT COUNT(*) FROM bookings b WHERE b.car_id = c.id AND b.status = 'pending') AS pending_count
                FROM cars c WHERE c.owner_id = ? ORDER BY c.id DESC""", (uid,)))
    return ok({"items": [serialize(c) for c in items]})


def _values(d: CarIn) -> tuple:
    return (d.brand, d.model, d.year, d.color, d.body_type, d.seats, d.transmission, d.fuel, d.engine_l, d.mileage_km,
            d.drive, json.dumps(d.features), d.city, d.description, d.price_per_day, d.deposit, d.min_days, d.max_days,
            d.km_limit, d.delivery_price, int(d.is_active))


FIELDS = ("brand, model, year, color, body_type, seats, transmission, fuel, engine_l, mileage_km, drive, features, city, "
          "description, price_per_day, deposit, min_days, max_days, km_limit, delivery_price, is_active")


@require("user")
async def create_car(request: Request):
    """Har qanday foydalanuvchi o'z avtomobilini e'lon qila oladi (alohida owner akkaunt shart emas)."""
    data = await parse_body(request, CarIn)
    uid = request.state.user["id"]
    with get_db() as db:
        cur = db.execute(f"INSERT INTO cars (owner_id, {FIELDS}) VALUES (?{', ?' * 21})", (uid, *_values(data)))
        # Birinchi e'londan keyin foydalanuvchi owner rejimiga o'tadi (faqat interfeys holati)
        db.execute("UPDATE users SET active_mode = 'owner' WHERE id = ?", (uid,))
        car = get_car_row(db, cur.lastrowid, uid)
    return ok(car, 201)


@require("user")
async def update_car(request: Request):
    car_id = path_int(request)
    data = await parse_body(request, CarIn)
    sets = ", ".join(f"{f.strip()} = ?" for f in FIELDS.split(","))
    with get_db() as db:
        own_car(db, car_id, request.state.user)
        db.execute(f"UPDATE cars SET {sets}, updated_at = datetime('now') WHERE id = ?", (*_values(data), car_id))
        car = get_car_row(db, car_id, request.state.user["id"])
    return ok(car)


@require("user", "admin")
async def delete_car(request: Request):
    car_id = path_int(request)
    user = request.state.user
    with get_db() as db:
        car = get_car_row(db, car_id) if user["role"] == "admin" else own_car(db, car_id, user)
        upcoming = db.execute("SELECT COUNT(*) FROM bookings WHERE car_id = ? AND status = 'approved' AND end_date >= ?",
                              (car_id, today().isoformat())).fetchone()[0]
        if upcoming and user["role"] != "admin":
            raise HTTPException(409, tr("Bu avtomobilda tasdiqlangan kelgusi bronlar bor. Avval ularni yakunlang "
                                        "yoki e'lonni vaqtincha yashiring"))
        paths = [r[0] for r in db.execute("SELECT path FROM car_images WHERE car_id = ?", (car_id,))]
        db.execute("DELETE FROM cars WHERE id = ?", (car_id,))
        if user["role"] == "admin":
            audit(db, request, "car_deleted", "car", car_id, title=car["title"])
    for p in paths:
        _remove_file(p)
    return ok({"deleted": car["id"]})


def _remove_file(public_path: str) -> None:
    target = settings.UPLOAD_DIR / public_path.rsplit("/", 1)[-1]
    if target.is_file() and target.resolve().parent == settings.UPLOAD_DIR.resolve():
        target.unlink(missing_ok=True)


@require("user")
async def upload_images(request: Request):
    car_id = path_int(request)
    max_bytes = settings.MAX_IMAGE_MB * 1024 * 1024
    with get_db() as db:
        own_car(db, car_id, request.state.user)
        existing = db.execute("SELECT COUNT(*) FROM car_images WHERE car_id = ?", (car_id,)).fetchone()[0]
    async with request.form(max_files=settings.MAX_IMAGES_PER_CAR, max_fields=10) as form:
        files = [f for f in form.getlist("images") if hasattr(f, "read")]
        labels = [str(x) for x in form.getlist("labels")]
        if not files:
            raise HTTPException(400, tr("Rasm tanlanmagan"))
        if existing + len(files) > settings.MAX_IMAGES_PER_CAR:
            raise HTTPException(400, tr("Bitta e'longa ko'pi bilan {n} ta rasm yuklash mumkin", n=settings.MAX_IMAGES_PER_CAR))
        saved = []
        for f in files:
            content = await f.read(max_bytes + 1)
            if len(content) > max_bytes:
                raise HTTPException(413, tr("Har bir rasm {n} MB dan oshmasligi kerak", n=settings.MAX_IMAGE_MB))
            if not _image_ext(content[:16]):
                raise HTTPException(400, tr("Faqat JPG, PNG yoki WEBP rasm yuklash mumkin"))
            try:
                clean = reencode_image(content)
            except ValueError:
                raise HTTPException(400, tr("Faqat JPG, PNG yoki WEBP rasm yuklash mumkin"))
            name = secrets.token_hex(16) + ".jpg"   # nomni server yaratadi
            (settings.UPLOAD_DIR / name).write_bytes(clean)
            saved.append("/uploads/" + name)
    with get_db() as db, transaction(db):
        for i, p in enumerate(saved):
            label = labels[i] if i < len(labels) and labels[i] in IMAGE_LABELS else "other"
            db.execute("INSERT INTO car_images (car_id, path, position, label) VALUES (?, ?, ?, ?)", (car_id, p, existing + i, label))
    with get_db() as db:
        images = rows(db.execute("SELECT id, path, label FROM car_images WHERE car_id = ? ORDER BY position, id", (car_id,)))
    return ok({"images": images}, 201)


@require("user")
async def delete_image(request: Request):
    car_id, img_id = path_int(request), path_int(request, "img_id")
    with get_db() as db:
        own_car(db, car_id, request.state.user)
        img = one(db.execute("SELECT path FROM car_images WHERE id = ? AND car_id = ?", (img_id, car_id)))
        if not img:
            raise HTTPException(404, tr("Rasm topilmadi"))
        db.execute("DELETE FROM car_images WHERE id = ?", (img_id,))
    _remove_file(img["path"])
    return ok()


@require("user")
async def cover_image(request: Request):
    """Asosiy rasmni belgilash: tanlangan rasm birinchi o'ringa o'tadi."""
    car_id, img_id = path_int(request), path_int(request, "img_id")
    with get_db() as db:
        own_car(db, car_id, request.state.user)
        ids = [r[0] for r in db.execute("SELECT id FROM car_images WHERE car_id = ? ORDER BY position, id", (car_id,))]
        if img_id not in ids:
            raise HTTPException(404, tr("Rasm topilmadi"))
        ids.remove(img_id)
        with transaction(db):
            for pos, i in enumerate([img_id] + ids):
                db.execute("UPDATE car_images SET position = ? WHERE id = ?", (pos, i))
        images = rows(db.execute("SELECT id, path, label FROM car_images WHERE car_id = ? ORDER BY position, id", (car_id,)))
    return ok({"images": images})


# ---------------- Sevimlilar ----------------
@require()
async def favorites(request: Request):
    uid = request.state.user["id"]
    with get_db() as db:
        items = rows(db.execute(
            f"SELECT {CAR_COLUMNS}, 1 AS is_favorite FROM favorites f JOIN cars c ON c.id = f.car_id JOIN users u ON u.id = c.owner_id "
            f"WHERE f.user_id = ? AND {PUBLIC_WHERE} ORDER BY f.created_at DESC", (uid,)))
    return ok({"items": [serialize(c) for c in items]})


@require()
async def add_favorite(request: Request):
    car_id = path_int(request)
    with get_db() as db:
        get_car_row(db, car_id)
        db.execute("INSERT OR IGNORE INTO favorites (user_id, car_id) VALUES (?, ?)", (request.state.user["id"], car_id))
    return ok({"car_id": car_id, "is_favorite": True})


@require()
async def remove_favorite(request: Request):
    car_id = path_int(request)
    with get_db() as db:
        db.execute("DELETE FROM favorites WHERE user_id = ? AND car_id = ?", (request.state.user["id"], car_id))
    return ok({"car_id": car_id, "is_favorite": False})


routes = [
    Route("/api/meta", meta, methods=["GET"]),
    Route("/api/cars", list_cars, methods=["GET"]),
    Route("/api/cars", create_car, methods=["POST"]),
    Route("/api/my/cars", my_cars, methods=["GET"]),
    Route("/api/cars/{id:int}", get_car, methods=["GET"]),
    Route("/api/cars/{id:int}", update_car, methods=["PUT"]),
    Route("/api/cars/{id:int}", delete_car, methods=["DELETE"]),
    Route("/api/cars/{id:int}/calendar", calendar, methods=["GET"]),
    Route("/api/cars/{id:int}/reviews", car_reviews, methods=["GET"]),
    Route("/api/cars/{id:int}/images", upload_images, methods=["POST"]),
    Route("/api/cars/{id:int}/images/{img_id:int}", delete_image, methods=["DELETE"]),
    Route("/api/cars/{id:int}/images/{img_id:int}/cover", cover_image, methods=["POST"]),
    Route("/api/cars/{id:int}/images/{img_id:int}", label_image, methods=["PATCH"]),
    Route("/api/cars/{id:int}/images/order", reorder_images, methods=["PUT"]),
    Route("/api/cars/{id:int}/blocks", list_blocks, methods=["GET"]),
    Route("/api/cars/{id:int}/blocks", add_block, methods=["POST"]),
    Route("/api/cars/{id:int}/blocks/{block_id:int}", delete_block, methods=["DELETE"]),
    Route("/api/favorites", favorites, methods=["GET"]),
    Route("/api/favorites/{id:int}", add_favorite, methods=["PUT"]),
    Route("/api/favorites/{id:int}", remove_favorite, methods=["DELETE"]),
]
