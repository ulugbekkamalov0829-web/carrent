"""Bron: narx serverda hisoblanadi va muzlatiladi, komissiya owner ulushidan ushlanadi, to'qnashuvlar bloklanadi.

Holatlar: pending -> approved | rejected | cancelled; approved -> cancelled | completed.
pending so'rov sanalarni 24 soat band qilib turadi; owner javob bermasa avtomatik rad etiladi.
"""
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.routing import Route

from ..db import get_db, get_setting, one, rows, transaction
from ..i18n import tr
from ..schemas import BookingIn
from ..security import require
from ..utils import bps_split, car_title, complete_finished_bookings, notify, ok, parse_body, path_int, q_str, today

MAX_PENDING_PER_USER = 3
PENDING_HOLD_HOURS = 24

BOOKING_SELECT = """
    SELECT b.*, c.brand, c.model, c.year, c.city, c.owner_id,
           (SELECT path FROM car_images i WHERE i.car_id = c.id ORDER BY position, id LIMIT 1) AS cover,
           ru.full_name AS renter_name, ru.phone AS renter_phone,
           ou.full_name AS owner_name, ou.phone AS owner_phone,
           (SELECT ROUND(AVG(rating), 1) FROM reviews rr WHERE rr.target_user_id = b.renter_id AND rr.kind = 'renter') AS renter_rating,
           (SELECT COUNT(*) FROM reviews rr WHERE rr.target_user_id = b.renter_id AND rr.kind = 'renter') AS renter_reviews,
           (SELECT id FROM reviews rv WHERE rv.booking_id = b.id AND rv.kind = 'car') AS car_review_id,
           (SELECT id FROM reviews rv WHERE rv.booking_id = b.id AND rv.kind = 'renter') AS renter_review_id,
           (SELECT id FROM payments p WHERE p.booking_id = b.id AND p.status IN ('paid', 'refunded', 'refund_pending')
             ORDER BY p.id DESC LIMIT 1) AS payment_id,
           ru.phone_verified AS renter_phone_verified, ru.email_verified AS renter_email_verified
    FROM bookings b
    JOIN cars c   ON c.id = b.car_id
    JOIN users ru ON ru.id = b.renter_id
    JOIN users ou ON ou.id = c.owner_id
"""


def maintain(db) -> None:
    """Fon vazifa o'rnida (har o'qishda arzon): yakunlangan ijaralar va muddati o'tgan so'rovlar."""
    complete_finished_bookings(db)
    from .payments import maintain_payments
    maintain_payments(db)
    expired = rows(db.execute(
        f"""SELECT b.id, b.renter_id, c.brand, c.model, c.year FROM bookings b JOIN cars c ON c.id = b.car_id
            WHERE b.status = 'pending' AND (b.created_at < datetime('now', '-{PENDING_HOLD_HOURS} hours') OR b.start_date < ?)""",
        (today().isoformat(),)))
    for e in expired:
        db.execute("UPDATE bookings SET status = 'rejected', updated_at = datetime('now') WHERE id = ? AND status = 'pending'",
                   (e["id"],))
        notify(db, e["renter_id"], "booking_expired", "/dashboard.html#bookings", car=car_title(e))


def _blocked(db, car_id: int, start: str, end: str) -> bool:
    """Owner o'zi yopib qo'ygan kunlar (ta'mir, shaxsiy foydalanish)."""
    return db.execute("SELECT 1 FROM car_blocks WHERE car_id = ? AND start_date <= ? AND end_date >= ? LIMIT 1",
                      (car_id, end, start)).fetchone() is not None


def _overlap(db, car_id: int, start: str, end: str, exclude_id: int | None = None, statuses=("approved", "pending")) -> bool:
    """Ikki oraliq kesishadi, agar: mavjud.boshi <= yangi.oxiri VA mavjud.oxiri >= yangi.boshi"""
    if _blocked(db, car_id, start, end):
        return True
    marks = ",".join("?" * len(statuses))
    sql = f"SELECT 1 FROM bookings WHERE car_id = ? AND status IN ({marks}) AND start_date <= ? AND end_date >= ?"
    params = [car_id, *statuses, end, start]
    if exclude_id:
        sql += " AND id != ?"; params.append(exclude_id)
    return db.execute(sql + " LIMIT 1", params).fetchone() is not None


def quote(car: dict, days: int, delivery: bool, bps: int) -> dict:
    """Narx hisob-kitobi (frontenddagi ko'rsatkich ham shu formuladan): har bir qator alohida."""
    rent = days * car["price_per_day"]
    delivery_fee = (car["delivery_price"] or 0) if delivery else 0
    total = rent + delivery_fee
    commission, payout = bps_split(total, bps)
    return {"days": days, "price_per_day": car["price_per_day"], "rent": rent, "delivery": delivery_fee, "total": total,
            "commission_bps": bps, "commission": commission, "owner_payout": payout, "deposit": car["deposit"],
            "pay_now": 0, "pay_on_site": total + car["deposit"]}


@require("user")
async def create_booking(request: Request):
    data = await parse_body(request, BookingIn)
    user = request.state.user
    if data.start_date < today():
        raise HTTPException(400, tr("O'tib ketgan sanani bron qilib bo'lmaydi"))
    if data.end_date < data.start_date:
        raise HTTPException(400, tr("Tugash sanasi boshlanish sanasidan oldin bo'lmasligi kerak"))
    days = (data.end_date - data.start_date).days + 1
    start, end = data.start_date.isoformat(), data.end_date.isoformat()

    with get_db() as db:
        maintain(db)
        # BEGIN IMMEDIATE: tekshirish va yozish orasida boshqa so'rov aralasha olmaydi (parallel bron himoyasi)
        with transaction(db, immediate=True):
            car = one(db.execute("SELECT c.*, u.is_active AS owner_active FROM cars c JOIN users u ON u.id = c.owner_id "
                                 "WHERE c.id = ?", (data.car_id,)))
            if not car or not (car["is_active"] and car["is_approved"] and car["owner_active"]):
                raise HTTPException(404, tr("Avtomobil topilmadi yoki hozir ijaraga berilmaydi"))
            if car["owner_id"] == user["id"]:
                raise HTTPException(400, tr("O'z avtomobilingizni bron qila olmaysiz"))
            if not car["min_days"] <= days <= car["max_days"]:
                raise HTTPException(400, tr("Bu avtomobil uchun ijara muddati {min}–{max} kun", min=car["min_days"], max=car["max_days"]))
            if data.delivery and car["delivery_price"] is None:
                raise HTTPException(400, tr("Bu avtomobilda yetkazib berish xizmati yo'q"))
            if _overlap(db, car["id"], start, end):
                raise HTTPException(409, tr("Tanlangan sanalarda avtomobil band. Kalendardan bo'sh kunlarni tanlang"))
            pending = db.execute("SELECT COUNT(*) FROM bookings WHERE renter_id = ? AND status = 'pending'", (user["id"],)).fetchone()[0]
            if pending >= MAX_PENDING_PER_USER:
                raise HTTPException(429, tr("Bir vaqtda ko'pi bilan {n} ta kutilayotgan so'rov yuborish mumkin", n=MAX_PENDING_PER_USER))
            q = quote(car, days, data.delivery, int(get_setting(db, "commission_bps", "1000")))
            cur = db.execute(
                """INSERT INTO bookings (car_id, renter_id, start_date, end_date, days, price_per_day, delivery, total_price,
                   commission_bps, commission, owner_payout, deposit, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (car["id"], user["id"], start, end, days, q["price_per_day"], q["delivery"], q["total"],
                 q["commission_bps"], q["commission"], q["owner_payout"], q["deposit"], data.note))
            bid = cur.lastrowid
            notify(db, car["owner_id"], "booking_new", "/dashboard.html?mode=owner#bookings", actor_id=user["id"],
                   name=user["full_name"], car=car_title(car), start=start, end=end, days=days, total=q["total"])
        booking = one(db.execute(BOOKING_SELECT + " WHERE b.id = ?", (bid,)))
    return ok(booking, 201)


async def quote_endpoint(request: Request):
    """Bron qilishdan oldin narxni ko'rsatish uchun: hisob serverda, frontend faqat ko'rsatadi."""
    from ..utils import q_date
    car_id = int(request.path_params["id"])
    s, e = q_date(request, "start"), q_date(request, "end")
    with get_db() as db:
        car = one(db.execute("SELECT * FROM cars WHERE id = ?", (car_id,)))
        if not car:
            raise HTTPException(404, tr("E'lon topilmadi"))
        if not s or not e or e < s:
            raise HTTPException(400, tr("Tugash sanasi boshlanish sanasidan oldin bo'lmasligi kerak"))
        q = quote(car, (e - s).days + 1, request.query_params.get("delivery") == "1",
                  int(get_setting(db, "commission_bps", "1000")))
        q["available"] = not _overlap(db, car_id, s.isoformat(), e.isoformat())
        q["within_limits"] = car["min_days"] <= q["days"] <= car["max_days"]
    return ok(q)


@require()
async def my_bookings(request: Request):
    uid = request.state.user["id"]
    status = q_str(request, "status")
    with get_db() as db:
        maintain(db)
        sql, params = BOOKING_SELECT + " WHERE b.renter_id = ?", [uid]
        if status:
            sql += " AND b.status = ?"; params.append(status)
        items = rows(db.execute(sql + " ORDER BY b.id DESC", params))
    return ok({"items": items})


@require()
async def incoming_bookings(request: Request):
    """Owner'ga kelgan so'rovlar — faqat o'z avtomobillari (egalik filtri)."""
    uid = request.state.user["id"]
    status = q_str(request, "status")
    with get_db() as db:
        maintain(db)
        sql, params = BOOKING_SELECT + " WHERE c.owner_id = ?", [uid]
        if status:
            sql += " AND b.status = ?"; params.append(status)
        items = rows(db.execute(sql + " ORDER BY (b.status = 'pending') DESC, b.id DESC", params))
    return ok({"items": items})


def _load(db, bid: int) -> dict:
    b = one(db.execute(BOOKING_SELECT + " WHERE b.id = ?", (bid,)))
    if not b:
        raise HTTPException(404, tr("Bron topilmadi"))
    return b


@require()
async def approve(request: Request):
    bid = path_int(request)
    uid = request.state.user["id"]
    with get_db() as db:
        with transaction(db, immediate=True):
            b = _load(db, bid)
            if b["owner_id"] != uid:
                raise HTTPException(403, tr("Bu bron sizning avtomobilingizga tegishli emas"))
            if b["status"] != "pending":
                raise HTTPException(400, tr("Faqat kutilayotgan bronni tasdiqlash mumkin"))
            if b["start_date"] < today().isoformat():
                raise HTTPException(400, tr("Boshlanish sanasi o'tib ketgan. So'rovni rad eting"))
            if _overlap(db, b["car_id"], b["start_date"], b["end_date"], exclude_id=bid, statuses=("approved",)):
                raise HTTPException(409, tr("Bu sanalarda boshqa tasdiqlangan bron bor"))
            db.execute("UPDATE bookings SET status='approved', updated_at=datetime('now') WHERE id = ?", (bid,))
            notify(db, b["renter_id"], "booking_approved", "/dashboard.html?mode=renter#bookings", actor_id=uid,
                   car=car_title(b), start=b["start_date"], end=b["end_date"])
        return ok(_load(db, bid))


@require()
async def reject(request: Request):
    bid = path_int(request)
    with get_db() as db:
        with transaction(db):
            b = _load(db, bid)
            if b["owner_id"] != request.state.user["id"]:
                raise HTTPException(403, tr("Bu bron sizning avtomobilingizga tegishli emas"))
            if b["status"] != "pending":
                raise HTTPException(400, tr("Faqat kutilayotgan bronni rad etish mumkin"))
            db.execute("UPDATE bookings SET status='rejected', updated_at=datetime('now') WHERE id = ?", (bid,))
            notify(db, b["renter_id"], "booking_rejected", "/dashboard.html?mode=renter#bookings",
                   car=car_title(b), start=b["start_date"], end=b["end_date"])
        return ok(_load(db, bid))


@require()
async def cancel(request: Request):
    bid = path_int(request)
    with get_db() as db:
        with transaction(db):
            b = _load(db, bid)
            if b["renter_id"] != request.state.user["id"]:
                raise HTTPException(403, tr("Bu bron sizga tegishli emas"))
            if b["status"] not in ("pending", "approved"):
                raise HTTPException(400, tr("Bu bronni bekor qilib bo'lmaydi"))
            if b["status"] == "approved" and b["start_date"] <= today().isoformat():
                raise HTTPException(400, tr("Ijara boshlangan — bekor qilish uchun egasi bilan bog'laning"))
            db.execute("UPDATE bookings SET status='cancelled', updated_at=datetime('now') WHERE id = ?", (bid,))
            from .payments import refund_for_booking
            refund = refund_for_booking(db, b)   # onlayn to'langan bo'lsa, siyosat bo'yicha qaytariladi
            notify(db, b["owner_id"], "booking_cancelled", "/dashboard.html?mode=owner#bookings", actor_id=b["renter_id"],
                   name=b["renter_name"], car=car_title(b), start=b["start_date"], end=b["end_date"])
        return ok({**_load(db, bid), "refund": refund})


@require()
async def cancel_preview_endpoint(request: Request):
    """Bekor qilishdan oldin: qancha qaytariladi va nega (siyosat qoidasi)."""
    bid = path_int(request)
    with get_db() as db:
        b = _load(db, bid)
        if b["renter_id"] != request.state.user["id"]:
            raise HTTPException(403, tr("Bu bron sizga tegishli emas"))
        from .payments import cancel_preview
        return ok(cancel_preview(db, b))


routes = [
    Route("/api/bookings", create_booking, methods=["POST"]),
    Route("/api/cars/{id:int}/quote", quote_endpoint, methods=["GET"]),
    Route("/api/bookings/mine", my_bookings, methods=["GET"]),
    Route("/api/bookings/incoming", incoming_bookings, methods=["GET"]),
    Route("/api/bookings/{id:int}/approve", approve, methods=["POST"]),
    Route("/api/bookings/{id:int}/reject", reject, methods=["POST"]),
    Route("/api/bookings/{id:int}/cancel", cancel, methods=["POST"]),
    Route("/api/bookings/{id:int}/cancel-preview", cancel_preview_endpoint, methods=["GET"]),
]
