"""Batafsil ko'rish (drill-down): dashboard yoki hisobotdagi istalgan raqam/qator bosilganda — aynan o'sha raqam qaysi
yozuvlardan tashkil topganini ko'rsatadi (qaysi mashina, kimniki, kim ijaraga olgan, qachon, qancha — rasmlari bilan).

Bitta endpoint: GET /api/drill?scope=owner|renter|admin&entity=bookings|cars|users|payments|reviews|payouts&...filtrlar
Ko'rinish chegarasi (scope) serverda majburiy qo'yiladi:
  * owner  — faqat o'z mashinalari va ularning bronlari, to'lovlari, sharhlari;
  * renter — faqat o'z bronlari, to'lovlari va yozgan sharhlari;
  * admin  — hammasi (faqat admin roli).
Natija ro'yxati va xulosa (soni, jami summa, komissiya, owner ulushi) — dashboarddagi raqam bilan bir xil qoidada hisoblanadi.
"""
from datetime import date, timedelta

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.routing import Route

from ..db import get_db, rows
from ..i18n import tr
from ..security import require
from ..utils import ok, q_date, q_int, q_str, today
from .bookings import maintain

DONE = ("approved", "completed")
B_STATUSES = {"pending", "approved", "rejected", "cancelled", "completed"}
PAY_STATUSES = {"on_site", "paid", "refunded", "refund_pending"}
P_STATUSES = {"created", "pending", "paid", "cancelled", "refunded", "refund_pending", "failed"}
BODIES = {"sedan", "hatchback", "crossover", "suv", "minivan", "pickup", "coupe"}
LIMIT = 500
COVER = "(SELECT path FROM car_images i WHERE i.car_id = c.id ORDER BY position, id LIMIT 1)"


def _csv(request: Request, name: str, allowed: set) -> list[str]:
    raw = q_str(request, name, 200) or ""
    if raw == "done":
        return list(DONE)
    vals = [v for v in raw.split(",") if v]
    if any(v not in allowed for v in vals):
        raise HTTPException(400, tr("Filtr qiymati noto'g'ri"))
    return vals


def _in(col: str, vals: list) -> tuple[str, list]:
    return f" AND {col} IN ({','.join('?' * len(vals))})", list(vals)


def _date_filter(request: Request, col: str) -> tuple[str, list]:
    """from/to (kun oralig'i), month (YYYY-MM) yoki day (YYYY-MM-DD) — ustun sana bo'yicha."""
    sql, params = "", []
    if month := q_str(request, "month", 7):
        if len(month) != 7 or month[4] != "-" or not (month[:4] + month[5:]).isdigit():
            raise HTTPException(400, tr("Filtr qiymati noto'g'ri"))
        sql += f" AND substr({col}, 1, 7) = ?"; params.append(month)
    if day := q_date(request, "day"):
        sql += f" AND date({col}) = ?"; params.append(day.isoformat())
    if d := q_date(request, "from"):
        sql += f" AND date({col}) >= ?"; params.append(d.isoformat())
    if d := q_date(request, "to"):
        sql += f" AND date({col}) <= ?"; params.append(d.isoformat())
    if days := q_int(request, "last_days", None, lo=1, hi=3660):
        sql += f" AND date({col}) >= ?"; params.append((today() - timedelta(days=days - 1)).isoformat())
    return sql, params


def _scope(request: Request) -> tuple[str, int]:
    scope = q_str(request, "scope") or "renter"
    user = request.state.user
    if scope not in ("owner", "renter", "admin"):
        raise HTTPException(400, tr("Filtr qiymati noto'g'ri"))
    if scope == "admin" and user["role"] != "admin":
        raise HTTPException(403, tr("Bu amal uchun huquqingiz yo'q"))
    return scope, user["id"]


def _common_car_filters(request: Request) -> tuple[str, list]:
    sql, params = "", []
    if city := q_str(request, "city"):
        sql += " AND c.city = ?"; params.append(city)
    if body := q_str(request, "body"):
        if body not in BODIES:
            raise HTTPException(400, tr("Filtr qiymati noto'g'ri"))
        sql += " AND c.body_type = ?"; params.append(body)
    if cid := q_int(request, "car_id", None, lo=1):
        sql += " AND c.id = ?"; params.append(cid)
    if oid := q_int(request, "owner_id", None, lo=1):
        sql += " AND c.owner_id = ?"; params.append(oid)
    return sql, params


# ---------------- Bronlar ----------------
def drill_bookings(db, request: Request, scope: str, uid: int) -> dict:
    where, params = {"owner": ("c.owner_id = ?", [uid]), "renter": ("b.renter_id = ?", [uid]), "admin": ("1 = 1", [])}[scope]
    s, p = _common_car_filters(request); where += s; params += p
    if st := _csv(request, "status", B_STATUSES):
        s, p = _in("b.status", st); where += s; params += p
    if ps := _csv(request, "pay", PAY_STATUSES):
        s, p = _in("b.payment_status", ps); where += s; params += p
    if rid := q_int(request, "renter_id", None, lo=1):
        where += " AND b.renter_id = ?"; params.append(rid)
    if scope == "admin" and (any_uid := q_int(request, "user_id", None, lo=1)):
        where += " AND (b.renter_id = ? OR c.owner_id = ?)"; params += [any_uid, any_uid]
    if q_str(request, "upcoming"):
        where += " AND b.end_date >= ?"; params.append(today().isoformat())
    if q_str(request, "unreviewed"):
        where += " AND NOT EXISTS (SELECT 1 FROM reviews r WHERE r.booking_id = b.id AND r.kind = 'car')"
    col = "b.created_at" if q_str(request, "date_field") == "created" else "b.start_date"
    s, p = _date_filter(request, col); where += s; params += p
    items = rows(db.execute(
        f"""SELECT b.id, b.start_date, b.end_date, b.days, b.status, b.payment_status, b.total_price, b.commission, b.owner_payout,
                   b.price_per_day, b.delivery, b.created_at, b.note,
                   c.id AS car_id, c.brand, c.model, c.year, c.city, c.district, c.body_type, {COVER} AS cover,
                   b.renter_id, ru.full_name AS renter_name, ru.avatar AS renter_avatar, ru.phone AS renter_phone,
                   c.owner_id, ou.full_name AS owner_name, ou.avatar AS owner_avatar, ou.phone AS owner_phone,
                   (SELECT COALESCE(SUM(p.refund_amount), 0) FROM payments p WHERE p.booking_id = b.id) AS refunded
            FROM bookings b JOIN cars c ON c.id = b.car_id JOIN users ru ON ru.id = b.renter_id JOIN users ou ON ou.id = c.owner_id
            WHERE {where} ORDER BY b.start_date DESC, b.id DESC LIMIT {LIMIT + 1}""", params))
    summary = dict(db.execute(
        f"""SELECT COUNT(*) AS count, COALESCE(SUM(b.total_price), 0) AS total, COALESCE(SUM(b.commission), 0) AS commission,
                   COALESCE(SUM(b.owner_payout), 0) AS payout, COALESCE(SUM(b.days), 0) AS days,
                   COUNT(DISTINCT b.car_id) AS cars, COUNT(DISTINCT b.renter_id) AS renters, COUNT(DISTINCT c.owner_id) AS owners
            FROM bookings b JOIN cars c ON c.id = b.car_id WHERE {where}""", params).fetchone())
    for it in items:
        if scope == "renter":          # ijarachi platforma va owner ulushini ko'rmaydi
            it.pop("commission"); it.pop("owner_payout")
        if scope != "admin":           # telefon raqamlari faqat bron sahifasida, shartlarga ko'ra
            it.pop("renter_phone"); it.pop("owner_phone")
    if scope == "renter":
        summary.pop("commission"); summary.pop("payout"); summary.pop("owners")
    return {"items": items[:LIMIT], "more": len(items) > LIMIT, "summary": summary}


# ---------------- Mashinalar ----------------
def drill_cars(db, request: Request, scope: str, uid: int) -> dict:
    if scope == "renter":
        raise HTTPException(403, tr("Bu amal uchun huquqingiz yo'q"))
    where, params = ("c.owner_id = ?", [uid]) if scope == "owner" else ("1 = 1", [])
    s, p = _common_car_filters(request); where += s; params += p
    state = q_str(request, "state")
    if state == "active":
        where += " AND c.is_active = 1 AND c.is_approved = 1"
    elif state == "hidden":
        where += " AND (c.is_active = 0 OR c.is_approved = 0)"
    elif state == "moderated":
        where += " AND c.is_approved = 0"
    s, p = _date_filter(request, "c.created_at") if q_str(request, "date_field") == "created" else ("", [])
    where += s; params += p
    # Davr (bandlik va tushum uchun): berilmasa — oxirgi 30 kun
    start = q_date(request, "p_from") or today() - timedelta(days=29)
    end = q_date(request, "p_to") or today()
    if end < start:
        start, end = end, start
    span = (end - start).days + 1
    items = rows(db.execute(
        f"""SELECT c.id, c.brand, c.model, c.year, c.city, c.district, c.body_type, c.price_per_day, c.is_active, c.is_approved,
                   c.views, c.created_at, {COVER} AS cover, c.owner_id, u.full_name AS owner_name, u.avatar AS owner_avatar,
                   (SELECT ROUND(AVG(r.rating), 1) FROM reviews r WHERE r.car_id = c.id AND r.kind = 'car') AS rating,
                   (SELECT COUNT(*) FROM reviews r WHERE r.car_id = c.id AND r.kind = 'car') AS reviews
            FROM cars c JOIN users u ON u.id = c.owner_id WHERE {where} ORDER BY c.id DESC LIMIT {LIMIT}""", params))
    for c in items:
        busy = trips = gross = payout = 0
        for b in db.execute(f"""SELECT start_date, end_date, total_price, owner_payout FROM bookings WHERE car_id = ?
                                AND status IN {DONE} AND start_date <= ? AND end_date >= ?""", (c["id"], end.isoformat(), start.isoformat())):
            a, z = max(date.fromisoformat(b[0]), start), min(date.fromisoformat(b[1]), end)
            busy += (z - a).days + 1
            if start.isoformat() <= b[0] <= end.isoformat():
                trips += 1; gross += b[2]; payout += b[3]
        c.update(busy_days=busy, idle_days=span - busy, occupancy=round(100 * busy / span, 1), trips=trips, gross=gross, payout=payout)
    if q_str(request, "sort") == "occupancy":
        items.sort(key=lambda c: c["occupancy"])
    summary = {"count": len(items), "active": sum(1 for c in items if c["is_active"] and c["is_approved"]),
               "views": sum(c["views"] for c in items), "gross": sum(c["gross"] for c in items), "payout": sum(c["payout"] for c in items),
               "occupancy": round(sum(c["occupancy"] for c in items) / len(items), 1) if items else 0.0,
               "p_from": start.isoformat(), "p_to": end.isoformat()}
    return {"items": items, "more": False, "summary": summary}


# ---------------- Foydalanuvchilar (faqat admin) ----------------
def drill_users(db, request: Request, scope: str, uid: int) -> dict:
    if scope != "admin":
        raise HTTPException(403, tr("Bu amal uchun huquqingiz yo'q"))
    from .dashboard import USER_KINDS
    where, params = "1 = 1", []
    kind = q_str(request, "kind") or ""
    if kind == "all":                       # dashboarddagi "Jami foydalanuvchilar" — adminlarsiz
        where += " AND u.role = 'user'"
    elif kind:
        if kind not in USER_KINDS:
            raise HTTPException(400, tr("Filtr qiymati noto'g'ri"))
        where += " AND " + USER_KINDS[kind]
    if region := q_str(request, "region"):
        where += " AND u.region = ?"; params.append(region)
    s, p = _date_filter(request, "u.created_at"); where += s; params += p
    items = rows(db.execute(
        f"""SELECT u.id, u.full_name, u.email, u.phone, u.avatar, u.role, u.is_active, u.created_at, u.region, u.district,
                   u.email_verified, u.phone_verified,
                   (SELECT COUNT(*) FROM cars c WHERE c.owner_id = u.id) AS cars,
                   (SELECT COUNT(*) FROM bookings b WHERE b.renter_id = u.id) AS bookings,
                   (SELECT COUNT(*) FROM reports r WHERE r.status = 'new' AND (
                        (r.target_type = 'user' AND r.target_id = u.id)
                     OR (r.target_type = 'car' AND r.target_id IN (SELECT id FROM cars WHERE owner_id = u.id)))) AS complaints
            FROM users u WHERE {where} ORDER BY u.id DESC LIMIT {LIMIT}""", params))
    return {"items": items, "more": False, "summary": {"count": len(items), "blocked": sum(1 for u in items if not u["is_active"])}}


# ---------------- To'lovlar ----------------
def drill_payments(db, request: Request, scope: str, uid: int) -> dict:
    where, params = {"owner": ("c.owner_id = ?", [uid]), "renter": ("p.user_id = ?", [uid]), "admin": ("1 = 1", [])}[scope]
    s, p = _common_car_filters(request); where += s; params += p
    st = _csv(request, "status", P_STATUSES) or ["paid", "refunded", "refund_pending"]
    s, p = _in("p.status", st); where += s; params += p
    if prov := q_str(request, "provider"):
        if prov not in ("test", "click", "payme"):
            raise HTTPException(400, tr("Filtr qiymati noto'g'ri"))
        where += " AND p.provider = ?"; params.append(prov)
    if scope == "admin" and (any_uid := q_int(request, "user_id", None, lo=1)):
        where += " AND (p.user_id = ? OR c.owner_id = ?)"; params += [any_uid, any_uid]
    col = "p.cancelled_at" if q_str(request, "date_field") == "cancelled" else "COALESCE(p.paid_at, p.created_at)"
    s, p = _date_filter(request, col); where += s; params += p
    items = rows(db.execute(
        f"""SELECT p.id, p.provider, p.amount, p.status, p.refund_amount, p.kept_commission, p.kept_payout, p.paid_at, p.created_at,
                   p.cancelled_at, b.id AS booking_id, b.start_date, b.end_date, b.commission, b.owner_payout,
                   c.id AS car_id, c.brand, c.model, c.year, c.city, {COVER} AS cover,
                   p.user_id AS renter_id, ru.full_name AS renter_name, ru.avatar AS renter_avatar,
                   c.owner_id, ou.full_name AS owner_name, ou.avatar AS owner_avatar
            FROM payments p JOIN bookings b ON b.id = p.booking_id JOIN cars c ON c.id = b.car_id
            JOIN users ru ON ru.id = p.user_id JOIN users ou ON ou.id = c.owner_id
            WHERE {where} ORDER BY p.id DESC LIMIT {LIMIT}""", params))
    if scope == "renter":
        for it in items:
            for k in ("commission", "owner_payout", "kept_commission", "kept_payout"):
                it.pop(k)
    return {"items": items, "more": False, "summary": {
        "count": len(items), "total": sum(i["amount"] for i in items), "refunded": sum(i["refund_amount"] for i in items)}}


# ---------------- Sharhlar ----------------
def drill_reviews(db, request: Request, scope: str, uid: int) -> dict:
    where, params = {"owner": ("c.owner_id = ? AND r.kind = 'car'", [uid]), "renter": ("r.author_id = ?", [uid]), "admin": ("1 = 1", [])}[scope]
    s, p = _common_car_filters(request); where += s; params += p
    if (rating := q_int(request, "rating", None, lo=1, hi=5)) is not None:
        where += " AND r.rating = ?"; params.append(rating)
    if scope == "admin" and (any_uid := q_int(request, "user_id", None, lo=1)):
        where += " AND (r.author_id = ? OR r.target_user_id = ?)"; params += [any_uid, any_uid]
    s, p = _date_filter(request, "r.created_at"); where += s; params += p
    items = rows(db.execute(
        f"""SELECT r.id, r.kind, r.rating, r.comment, r.reply, r.created_at, r.booking_id,
                   c.id AS car_id, c.brand, c.model, c.year, c.city, {COVER} AS cover,
                   r.author_id, a.full_name AS author_name, a.avatar AS author_avatar, r.target_user_id, tu.full_name AS target_name
            FROM reviews r JOIN cars c ON c.id = r.car_id JOIN users a ON a.id = r.author_id JOIN users tu ON tu.id = r.target_user_id
            WHERE {where} ORDER BY r.id DESC LIMIT {LIMIT}""", params))
    avg = round(sum(i["rating"] for i in items) / len(items), 2) if items else None
    return {"items": items, "more": False, "summary": {"count": len(items), "avg": avg}}


# ---------------- Owner'ga o'tkazmalar ----------------
def drill_payouts(db, request: Request, scope: str, uid: int) -> dict:
    if scope == "renter":
        raise HTTPException(403, tr("Bu amal uchun huquqingiz yo'q"))
    where, params = ("po.owner_id = ?", [uid]) if scope == "owner" else ("1 = 1", [])
    if scope == "admin" and (oid := q_int(request, "owner_id", None, lo=1)):
        where += " AND po.owner_id = ?"; params.append(oid)
    s, p = _date_filter(request, "po.created_at"); where += s; params += p
    items = rows(db.execute(
        f"""SELECT po.id, po.amount, po.note, po.created_at, po.owner_id, u.full_name AS owner_name, u.avatar AS owner_avatar,
                   cb.full_name AS created_by_name
            FROM payouts po JOIN users u ON u.id = po.owner_id LEFT JOIN users cb ON cb.id = po.created_by
            WHERE {where} ORDER BY po.id DESC LIMIT {LIMIT}""", params))
    return {"items": items, "more": False, "summary": {"count": len(items), "total": sum(i["amount"] for i in items)}}


ENTITIES = {"bookings": drill_bookings, "cars": drill_cars, "users": drill_users, "payments": drill_payments,
            "reviews": drill_reviews, "payouts": drill_payouts}


@require()
async def drill(request: Request):
    scope, uid = _scope(request)
    entity = q_str(request, "entity") or "bookings"
    if entity not in ENTITIES:
        raise HTTPException(400, tr("Filtr qiymati noto'g'ri"))
    with get_db() as db:
        maintain(db)
        data = ENTITIES[entity](db, request, scope, uid)
    return ok({"scope": scope, "entity": entity, **data})


routes = [Route("/api/drill", drill, methods=["GET"])]
