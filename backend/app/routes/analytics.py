"""Hisobotlar: owner, ijarachi va admin uchun tanlangan davr bo'yicha tushunarli hisobot.

Har bir hisobot:
  * kpis      — asosiy ko'rsatkichlar va o'tgan (teng uzunlikdagi) davrdagi qiymati: o'sish/kamayish ko'rinadi;
  * series    — vaqt bo'yicha grafik (62 kungacha — kunlik, undan uzun — oylik);
  * tables    — avtomobillar, shaharlar, to'lov usullari va h.k. bo'yicha taqsimot;
  * insights  — ma'lumotdan chiqarilgan oddiy tildagi xulosalar (kod + parametrlar, frontend uch tilga o'giradi).
Ijara davrga boshlanish sanasi bo'yicha tegishli (kabinetdagi grafiklar bilan bir xil qoida). Hamma raqam bazadagi yozuvlardan.
"""
import csv
import io
from datetime import date, timedelta

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from ..db import get_db, rows
from ..i18n import tr
from ..security import require
from ..utils import car_title, ok, q_date, today
from .bookings import maintain

DONE = "('approved', 'completed')"
MAX_DAYS = 366


# ---------------- Davr ----------------
def _period(request: Request) -> tuple[date, date, date, date]:
    """(boshi, oxiri, o'tgan_boshi, o'tgan_oxiri). Standart — joriy oy boshidan bugungacha."""
    t = today()
    start = q_date(request, "from") or t.replace(day=1)
    end = q_date(request, "to") or t
    if end < start:
        start, end = end, start
    if (end - start).days + 1 > MAX_DAYS:
        raise HTTPException(400, tr("Davr 366 kundan oshmasligi kerak"))
    length = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    return start, end, prev_end - timedelta(days=length - 1), prev_end


def _buckets(start: date, end: date) -> tuple[str, list[str]]:
    if (end - start).days <= 61:
        return "day", [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    out, d = [], start.replace(day=1)
    while d <= end:
        out.append(d.strftime("%Y-%m"))
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return "month", out


def _series(db, sql_where: str, params: list, value_sql: str, start: date, end: date) -> dict:
    unit, keys = _buckets(start, end)
    key_sql = "b.start_date" if unit == "day" else "substr(b.start_date, 1, 7)"
    data = {r["k"]: r for r in rows(db.execute(
        f"""SELECT {key_sql} AS k, COALESCE(SUM({value_sql}), 0) AS v, COUNT(*) AS n
            FROM bookings b JOIN cars c ON c.id = b.car_id
            WHERE {sql_where} AND b.status IN {DONE} AND b.start_date BETWEEN ? AND ? GROUP BY k""",
        params + [start.isoformat(), end.isoformat()]))}
    return {"unit": unit, "points": [{"k": k, "v": (data.get(k) or {}).get("v", 0), "n": (data.get(k) or {}).get("n", 0)} for k in keys]}


def _overlap_days(s: str, e: str, start: date, end: date) -> int:
    a, b = max(date.fromisoformat(s), start), min(date.fromisoformat(e), end)
    return max(0, (b - a).days + 1)


def _kpi(code: str, value, prev, fmt: str = "int", good_when_up: bool = True) -> dict:
    change = None
    if isinstance(value, (int, float)) and isinstance(prev, (int, float)) and prev:
        change = round(100 * (value - prev) / prev, 1)
    return {"code": code, "value": value, "prev": prev, "change": change, "fmt": fmt, "up_good": good_when_up}


def _weekday(db, where: str, params: list, start: date, end: date) -> int | None:
    r = db.execute(f"""SELECT CAST(strftime('%w', b.start_date) AS INTEGER) AS w, COUNT(*) AS n FROM bookings b JOIN cars c ON c.id = b.car_id
                       WHERE {where} AND b.status IN {DONE} AND b.start_date BETWEEN ? AND ? GROUP BY w ORDER BY n DESC LIMIT 1""",
                   params + [start.isoformat(), end.isoformat()]).fetchone()
    return r[0] if r and r[1] >= 2 else None


# ---------------- Owner ----------------
def _funnel(db, where: str, params: list, A: str, B: str) -> dict:
    """Davrda yaratilgan bronlar holat bo'yicha (so'rov -> tasdiq -> yakun / rad / bekor)."""
    out = {s: 0 for s in ("pending", "approved", "completed", "rejected", "cancelled")}
    for st, n in db.execute(f"SELECT b.status, COUNT(*) FROM bookings b JOIN cars c ON c.id = b.car_id "
                            f"WHERE {where} AND date(b.created_at) BETWEEN ? AND ? GROUP BY b.status", [*params, A, B]):
        out[st] = n
    return out


def owner_report(db, uid: int, start: date, end: date, ps: date, pe: date) -> dict:
    def money(a: date, b: date) -> dict:
        r = db.execute(f"""SELECT COUNT(*), COALESCE(SUM(b.total_price), 0), COALESCE(SUM(b.commission), 0), COALESCE(SUM(b.owner_payout), 0),
                                  COALESCE(SUM(b.days), 0) FROM bookings b JOIN cars c ON c.id = b.car_id
                           WHERE c.owner_id = ? AND b.status IN {DONE} AND b.start_date BETWEEN ? AND ?""",
                       (uid, a.isoformat(), b.isoformat())).fetchone()
        comp = db.execute("""SELECT COALESCE(SUM(p.kept_payout), 0) FROM payments p JOIN bookings b ON b.id = p.booking_id JOIN cars c ON c.id = b.car_id
                             WHERE c.owner_id = ? AND b.status = 'cancelled' AND p.kept_payout > 0 AND b.start_date BETWEEN ? AND ?""",
                          (uid, a.isoformat(), b.isoformat())).fetchone()[0]
        lost = db.execute("""SELECT COUNT(*) FROM bookings b JOIN cars c ON c.id = b.car_id
                             WHERE c.owner_id = ? AND b.status IN ('cancelled', 'rejected') AND b.start_date BETWEEN ? AND ?""",
                          (uid, a.isoformat(), b.isoformat())).fetchone()[0]
        return {"trips": r[0], "gross": r[1], "commission": r[2], "payout": r[3] + comp, "days": r[4], "comp": comp, "lost": lost}

    cur, prev = money(start, end), money(ps, pe)
    cars = rows(db.execute("SELECT id, brand, model, year, city, price_per_day, created_at FROM cars WHERE owner_id = ? ORDER BY id", (uid,)))
    span = (end - start).days + 1
    per_car = []
    for c in cars:
        bs = rows(db.execute(f"""SELECT start_date, end_date, days, total_price, owner_payout FROM bookings
                                 WHERE car_id = ? AND status IN {DONE} AND start_date <= ? AND end_date >= ?""",
                             (c["id"], end.isoformat(), start.isoformat())))
        busy = sum(_overlap_days(b["start_date"], b["end_date"], start, end) for b in bs)
        in_period = [b for b in bs if start.isoformat() <= b["start_date"] <= end.isoformat()]
        rating = db.execute("SELECT ROUND(AVG(rating), 1) FROM reviews WHERE car_id = ? AND kind = 'car' AND date(created_at) BETWEEN ? AND ?",
                            (c["id"], start.isoformat(), end.isoformat())).fetchone()[0]
        per_car.append({"id": c["id"], "title": car_title(c), "city": c["city"], "price_per_day": c["price_per_day"],
                        "trips": len(in_period), "busy_days": busy, "idle_days": span - busy,
                        "occupancy": round(100 * busy / span, 1), "gross": sum(b["total_price"] for b in in_period),
                        "payout": sum(b["owner_payout"] for b in in_period), "rating": rating})
    per_car.sort(key=lambda x: x["payout"], reverse=True)
    occ = round(sum(c["occupancy"] for c in per_car) / len(per_car), 1) if per_car else 0.0
    prev_busy = 0
    for c in cars:
        for b in db.execute(f"SELECT start_date, end_date FROM bookings WHERE car_id = ? AND status IN {DONE} AND start_date <= ? AND end_date >= ?",
                            (c["id"], pe.isoformat(), ps.isoformat())):
            prev_busy += _overlap_days(b[0], b[1], ps, pe)
    prev_occ = round(100 * prev_busy / (span * len(cars)), 1) if cars else 0.0
    rating = db.execute("""SELECT ROUND(AVG(r.rating), 2), COUNT(*) FROM reviews r JOIN cars c ON c.id = r.car_id
                           WHERE c.owner_id = ? AND r.kind = 'car' AND date(r.created_at) BETWEEN ? AND ?""",
                        (uid, start.isoformat(), end.isoformat())).fetchone()
    pending = db.execute("SELECT COUNT(*) FROM bookings b JOIN cars c ON c.id = b.car_id WHERE c.owner_id = ? AND b.status = 'pending'",
                         (uid,)).fetchone()[0]

    kpis = [
        _kpi("income", cur["payout"], prev["payout"], "money"),
        _kpi("gross", cur["gross"], prev["gross"], "money"),
        _kpi("commission", cur["commission"], prev["commission"], "money", good_when_up=False),
        _kpi("trips", cur["trips"], prev["trips"]),
        _kpi("rental_days", cur["days"], prev["days"]),
        _kpi("occupancy", occ, prev_occ, "pct"),
        _kpi("avg_check", round(cur["gross"] / cur["trips"]) if cur["trips"] else 0,
             round(prev["gross"] / prev["trips"]) if prev["trips"] else 0, "money"),
        _kpi("lost", cur["lost"], prev["lost"], good_when_up=False),
    ]
    insights = []
    if not cur["trips"] and not cur["comp"]:
        insights.append({"code": "no_trips", "kind": "info"})
    else:
        if prev["payout"]:
            ch = round(100 * (cur["payout"] - prev["payout"]) / prev["payout"])
            insights.append({"code": "income_up" if ch >= 0 else "income_down", "kind": "good" if ch >= 0 else "warn",
                             "params": {"pct": abs(ch), "sum": cur["payout"], "prev": prev["payout"]}})
        else:
            insights.append({"code": "income_first", "kind": "good", "params": {"sum": cur["payout"], "n": cur["trips"]}})
        top = per_car[0] if per_car and per_car[0]["payout"] else None
        if top and len([c for c in per_car if c["payout"]]) > 1:
            insights.append({"code": "best_car", "kind": "good", "params": {
                "car": top["title"], "car_id": top["id"], "sum": top["payout"], "share": round(100 * top["payout"] / max(1, cur["payout"] - cur["comp"]))}})
        if cur["comp"]:
            insights.append({"code": "compensation", "kind": "info", "params": {"sum": cur["comp"]}})
    for c in per_car:
        if c["occupancy"] < 25 and span >= 7:
            insights.append({"code": "idle_car", "kind": "warn", "params": {"car": c["title"], "car_id": c["id"], "n": c["idle_days"], "pct": c["occupancy"]}})
    wd = _weekday(db, "c.owner_id = ?", [uid], start, end)
    if wd is not None:
        insights.append({"code": "busy_weekday", "kind": "info", "params": {"wd": wd}})
    total_req = cur["trips"] + cur["lost"]
    if total_req >= 4 and cur["lost"] / total_req > 0.3:
        insights.append({"code": "many_lost", "kind": "warn", "params": {"pct": round(100 * cur["lost"] / total_req)}})
    if pending:
        insights.append({"code": "pending_now", "kind": "action", "params": {"n": pending}, "link": "/dashboard.html#bookings"})
    if rating[1]:
        insights.append({"code": "rating", "kind": "good" if (rating[0] or 0) >= 4.5 else "info", "params": {"avg": rating[0], "n": rating[1]}})

    return {"kpis": kpis, "series": _series(db, "c.owner_id = ?", [uid], "b.owner_payout", start, end),
            "series_label": "income", "insights": insights,
            "tables": {"per_car": per_car, "funnel": _funnel(db, "c.owner_id = ?", [uid], start.isoformat(), end.isoformat())}}


# ---------------- Ijarachi ----------------
def renter_report(db, uid: int, start: date, end: date, ps: date, pe: date) -> dict:
    def agg(a: date, b: date) -> dict:
        r = db.execute(f"""SELECT COUNT(*), COALESCE(SUM(total_price), 0), COALESCE(SUM(days), 0) FROM bookings
                           WHERE renter_id = ? AND status IN {DONE} AND start_date BETWEEN ? AND ?""", (uid, a.isoformat(), b.isoformat())).fetchone()
        cancelled = db.execute("SELECT COUNT(*) FROM bookings WHERE renter_id = ? AND status = 'cancelled' AND start_date BETWEEN ? AND ?",
                               (uid, a.isoformat(), b.isoformat())).fetchone()[0]
        refunds = db.execute("""SELECT COALESCE(SUM(p.refund_amount), 0) FROM payments p JOIN bookings b ON b.id = p.booking_id
                                WHERE p.user_id = ? AND p.status IN ('refunded', 'refund_pending') AND b.start_date BETWEEN ? AND ?""",
                             (uid, a.isoformat(), b.isoformat())).fetchone()[0]
        return {"trips": r[0], "spent": r[1], "days": r[2], "cancelled": cancelled, "refunds": refunds}

    cur, prev = agg(start, end), agg(ps, pe)
    trips = rows(db.execute(
        """SELECT b.id, b.start_date, b.end_date, b.days, b.total_price, b.status, b.payment_status, c.id AS car_id,
                  c.brand, c.model, c.year, c.body_type, c.city, b.price_per_day
           FROM bookings b JOIN cars c ON c.id = b.car_id WHERE b.renter_id = ? AND b.start_date BETWEEN ? AND ? ORDER BY b.start_date DESC""",
        (uid, start.isoformat(), end.isoformat())))
    for tr_ in trips:
        tr_["title"] = car_title(tr_)
    done = [x for x in trips if x["status"] in ("approved", "completed")]
    by_body, by_city = {}, {}
    for x in done:
        by_body.setdefault(x["body_type"], {"key": x["body_type"], "trips": 0, "spent": 0})
        by_body[x["body_type"]]["trips"] += 1; by_body[x["body_type"]]["spent"] += x["total_price"]
        by_city.setdefault(x["city"], {"key": x["city"], "trips": 0, "spent": 0})
        by_city[x["city"]]["trips"] += 1; by_city[x["city"]]["spent"] += x["total_price"]
    avg_day = round(sum(x["price_per_day"] * x["days"] for x in done) / cur["days"]) if cur["days"] else 0
    prev_avg_day = round(prev["spent"] / prev["days"]) if prev["days"] else 0

    kpis = [
        _kpi("spent", cur["spent"], prev["spent"], "money", good_when_up=False),
        _kpi("trips", cur["trips"], prev["trips"]),
        _kpi("rental_days", cur["days"], prev["days"]),
        _kpi("avg_day", avg_day, prev_avg_day, "money", good_when_up=False),
        _kpi("refunds", cur["refunds"], prev["refunds"], "money"),
        _kpi("cancelled", cur["cancelled"], prev["cancelled"], good_when_up=False),
    ]
    insights = []
    if not done:
        insights.append({"code": "renter_none", "kind": "info", "link": "/advisor.html"})
    else:
        insights.append({"code": "renter_total", "kind": "info", "params": {"sum": cur["spent"], "n": cur["trips"], "days": cur["days"]}})
        if prev["spent"]:
            ch = round(100 * (cur["spent"] - prev["spent"]) / prev["spent"])
            insights.append({"code": "spent_up" if ch > 0 else "spent_down", "kind": "info" if ch > 0 else "good", "params": {"pct": abs(ch)}})
        fav = max(by_body.values(), key=lambda v: v["trips"])
        if fav["trips"] >= 2:
            insights.append({"code": "fav_body", "kind": "info", "params": {"body": fav["key"], "n": fav["trips"]}})
        # Bozor bilan solishtirish: siz tanlagan kuzov turidagi faol e'lonlarning o'rtacha kunlik narxi
        types = list(by_body)
        marks = ",".join("?" * len(types))
        market = db.execute(f"SELECT AVG(price_per_day) FROM cars WHERE is_active = 1 AND is_approved = 1 AND body_type IN ({marks})",
                            types).fetchone()[0]
        if market and avg_day:
            diff = round(100 * (avg_day - market) / market)
            if abs(diff) >= 5:
                insights.append({"code": "cheaper_than_market" if diff < 0 else "pricier_than_market", "kind": "good" if diff < 0 else "info",
                                 "params": {"pct": abs(diff), "avg": avg_day, "market": round(market)}})
    if cur["refunds"]:
        insights.append({"code": "renter_refunds", "kind": "good", "params": {"sum": cur["refunds"]}})
    to_review = db.execute("""SELECT COUNT(*) FROM bookings b WHERE b.renter_id = ? AND b.status = 'completed'
                              AND NOT EXISTS (SELECT 1 FROM reviews r WHERE r.booking_id = b.id AND r.kind = 'car')""", (uid,)).fetchone()[0]
    if to_review:
        insights.append({"code": "renter_review", "kind": "action", "params": {"n": to_review}, "link": "/dashboard.html#bookings"})
    return {"kpis": kpis, "series": _series(db, "b.renter_id = ?", [uid], "b.total_price", start, end), "series_label": "spent",
            "tables": {"trips": trips, "funnel": _funnel(db, "b.renter_id = ?", [uid], start.isoformat(), end.isoformat()),
                       "by_body": sorted(by_body.values(), key=lambda v: -v["spent"]),
                       "by_city": sorted(by_city.values(), key=lambda v: -v["spent"])}, "insights": insights}


# ---------------- Admin ----------------
def admin_report(db, start: date, end: date, ps: date, pe: date) -> dict:
    def agg(a: date, b: date) -> dict:
        A, B = a.isoformat(), b.isoformat()
        r = db.execute(f"""SELECT COUNT(*), COALESCE(SUM(total_price), 0), COALESCE(SUM(commission), 0) FROM bookings
                           WHERE status IN {DONE} AND start_date BETWEEN ? AND ?""", (A, B)).fetchone()
        kept = db.execute("""SELECT COALESCE(SUM(p.kept_commission), 0) FROM payments p JOIN bookings b ON b.id = p.booking_id
                             WHERE b.status = 'cancelled' AND b.start_date BETWEEN ? AND ?""", (A, B)).fetchone()[0]
        created = db.execute("SELECT COUNT(*), COALESCE(SUM(status IN ('cancelled', 'rejected')), 0) FROM bookings WHERE date(created_at) BETWEEN ? AND ?",
                             (A, B)).fetchone()
        online = db.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status IN ('paid', 'refunded', 'refund_pending') "
                            "AND date(paid_at) BETWEEN ? AND ?", (A, B)).fetchone()[0]
        refunds = db.execute("SELECT COALESCE(SUM(refund_amount), 0) FROM payments WHERE status IN ('refunded', 'refund_pending') "
                             "AND date(cancelled_at) BETWEEN ? AND ?", (A, B)).fetchone()[0]
        payouts = db.execute("SELECT COALESCE(SUM(amount), 0) FROM payouts WHERE date(created_at) BETWEEN ? AND ?", (A, B)).fetchone()[0]
        users = db.execute("SELECT COUNT(*) FROM users WHERE role = 'user' AND date(created_at) BETWEEN ? AND ?", (A, B)).fetchone()[0]
        cars = db.execute("SELECT COUNT(*) FROM cars WHERE date(created_at) BETWEEN ? AND ?", (A, B)).fetchone()[0]
        return {"trips": r[0], "gmv": r[1], "commission": r[2] + kept, "requests": created[0], "lost": created[1],
                "online": online, "refunds": refunds, "payouts": payouts, "users": users, "cars": cars}

    cur, prev = agg(start, end), agg(ps, pe)
    A, B = start.isoformat(), end.isoformat()
    by_city = rows(db.execute(f"""SELECT c.city AS key, COUNT(*) AS trips, SUM(b.total_price) AS gmv, SUM(b.commission) AS commission
                                  FROM bookings b JOIN cars c ON c.id = b.car_id WHERE b.status IN {DONE} AND b.start_date BETWEEN ? AND ?
                                  GROUP BY c.city ORDER BY gmv DESC LIMIT 10""", (A, B)))
    top_owners = rows(db.execute(f"""SELECT u.id, u.full_name AS name, COUNT(*) AS trips, SUM(b.owner_payout) AS payout, SUM(b.commission) AS commission
                                     FROM bookings b JOIN cars c ON c.id = b.car_id JOIN users u ON u.id = c.owner_id
                                     WHERE b.status IN {DONE} AND b.start_date BETWEEN ? AND ? GROUP BY u.id ORDER BY payout DESC LIMIT 8""", (A, B)))
    top_cars = rows(db.execute(f"""SELECT c.id, c.brand, c.model, c.year, c.city, COUNT(*) AS trips, SUM(b.total_price) AS gmv
                                   FROM bookings b JOIN cars c ON c.id = b.car_id WHERE b.status IN {DONE} AND b.start_date BETWEEN ? AND ?
                                   GROUP BY c.id ORDER BY gmv DESC LIMIT 8""", (A, B)))
    for c in top_cars:
        c["title"] = car_title(c)
    providers = rows(db.execute("""SELECT provider AS key, COUNT(*) AS n, SUM(amount) AS amount FROM payments
                                   WHERE status IN ('paid', 'refunded', 'refund_pending') AND date(paid_at) BETWEEN ? AND ?
                                   GROUP BY provider ORDER BY amount DESC""", (A, B)))
    funnel = {s: 0 for s in ("pending", "approved", "completed", "rejected", "cancelled")}
    for s, n in db.execute("SELECT status, COUNT(*) FROM bookings WHERE date(created_at) BETWEEN ? AND ? GROUP BY status", (A, B)):
        funnel[s] = n
    to_do = {
        "refunds": db.execute("SELECT COUNT(*) FROM payments WHERE status = 'refund_pending'").fetchone()[0],
        "payout_requests": db.execute("SELECT COUNT(*) FROM payout_requests WHERE status = 'pending'").fetchone()[0],
        "reports": db.execute("SELECT COUNT(*) FROM reports WHERE status = 'new'").fetchone()[0],
    }
    lost_rate = round(100 * cur["lost"] / cur["requests"], 1) if cur["requests"] else 0.0
    prev_lost = round(100 * prev["lost"] / prev["requests"], 1) if prev["requests"] else 0.0
    kpis = [
        _kpi("gmv", cur["gmv"], prev["gmv"], "money"),
        _kpi("platform_income", cur["commission"], prev["commission"], "money"),
        _kpi("trips", cur["trips"], prev["trips"]),
        _kpi("avg_check", round(cur["gmv"] / cur["trips"]) if cur["trips"] else 0, round(prev["gmv"] / prev["trips"]) if prev["trips"] else 0, "money"),
        _kpi("online_paid", cur["online"], prev["online"], "money"),
        _kpi("refunds", cur["refunds"], prev["refunds"], "money", good_when_up=False),
        _kpi("payouts", cur["payouts"], prev["payouts"], "money"),
        _kpi("new_users", cur["users"], prev["users"]),
        _kpi("new_cars", cur["cars"], prev["cars"]),
        _kpi("lost_rate", lost_rate, prev_lost, "pct", good_when_up=False),
    ]
    insights = []
    if not cur["trips"]:
        insights.append({"code": "admin_none", "kind": "info"})
    else:
        if prev["gmv"]:
            ch = round(100 * (cur["gmv"] - prev["gmv"]) / prev["gmv"])
            insights.append({"code": "gmv_up" if ch >= 0 else "gmv_down", "kind": "good" if ch >= 0 else "warn",
                             "params": {"pct": abs(ch), "sum": cur["gmv"], "fee": cur["commission"]}})
        else:
            insights.append({"code": "gmv_first", "kind": "good", "params": {"sum": cur["gmv"], "fee": cur["commission"]}})
        if by_city:
            insights.append({"code": "top_city", "kind": "info", "params": {"city": by_city[0]["key"], "share": round(100 * by_city[0]["gmv"] / cur["gmv"])}})
        share = round(100 * cur["online"] / cur["gmv"]) if cur["gmv"] else 0
        insights.append({"code": "online_share", "kind": "good" if share >= 50 else "info", "params": {"pct": min(share, 100)}})
    if lost_rate > 30 and cur["requests"] >= 5:
        insights.append({"code": "admin_lost", "kind": "warn", "params": {"pct": lost_rate}})
    if cur["users"] and prev["users"] and cur["users"] > prev["users"]:
        insights.append({"code": "users_growth", "kind": "good", "params": {"n": cur["users"], "prev": prev["users"]}})
    for key, link in (("refunds", "/admin.html#payments"), ("payout_requests", "/admin.html#finance"), ("reports", "/admin.html#reports")):
        if to_do[key]:
            insights.append({"code": "todo_" + key, "kind": "action", "params": {"n": to_do[key]}, "link": link})
    return {"kpis": kpis, "series": _series(db, "1 = 1", [], "b.total_price", start, end),
            "series2": _series(db, "1 = 1", [], "b.commission", start, end), "series_label": "gmv",
            "tables": {"by_city": by_city, "top_owners": top_owners, "top_cars": top_cars, "providers": providers, "funnel": funnel},
            "insights": insights}


# ---------------- Endpointlar ----------------
def _build(request: Request, kind: str) -> dict:
    user = request.state.user
    if kind == "admin" and user["role"] != "admin":
        raise HTTPException(403, tr("Bu amal uchun huquqingiz yo'q"))
    if kind not in ("owner", "renter", "admin"):
        raise HTTPException(404, tr("Hisobot turi noto'g'ri"))
    start, end, ps, pe = _period(request)
    with get_db() as db:
        maintain(db)
        if kind == "owner":
            data = owner_report(db, user["id"], start, end, ps, pe)
        elif kind == "renter":
            data = renter_report(db, user["id"], start, end, ps, pe)
        else:
            data = admin_report(db, start, end, ps, pe)
    return {"kind": kind, "period": {"from": start.isoformat(), "to": end.isoformat(), "days": (end - start).days + 1},
            "prev": {"from": ps.isoformat(), "to": pe.isoformat()}, "generated": today().isoformat(), **data}


@require()
async def report(request: Request):
    return ok(_build(request, request.path_params["kind"]))


@require()
async def report_csv(request: Request):
    """Batafsil ro'yxat (Excel uchun, UTF-8 BOM): har bir bron alohida qator. Faqat foydalanuvchiga tegishli ma'lumot."""
    kind = request.path_params["kind"]
    user = request.state.user
    if kind == "admin" and user["role"] != "admin":
        raise HTTPException(403, tr("Bu amal uchun huquqingiz yo'q"))
    if kind not in ("owner", "renter", "admin"):
        raise HTTPException(404, tr("Hisobot turi noto'g'ri"))
    start, end, _, _ = _period(request)
    where, params = {"owner": ("c.owner_id = ?", [user["id"]]), "renter": ("b.renter_id = ?", [user["id"]]), "admin": ("1 = 1", [])}[kind]
    with get_db() as db:
        maintain(db)
        items = rows(db.execute(
            f"""SELECT b.id, b.start_date, b.end_date, b.days, b.status, b.payment_status, b.price_per_day, b.delivery, b.total_price,
                       b.commission, b.owner_payout, c.brand, c.model, c.year, c.city, ru.full_name AS renter, ou.full_name AS owner,
                       (SELECT COALESCE(SUM(p.refund_amount), 0) FROM payments p WHERE p.booking_id = b.id) AS refunded
                FROM bookings b JOIN cars c ON c.id = b.car_id JOIN users ru ON ru.id = b.renter_id JOIN users ou ON ou.id = c.owner_id
                WHERE {where} AND b.start_date BETWEEN ? AND ? ORDER BY b.start_date""", params + [start.isoformat(), end.isoformat()]))
    cols = [("id", "Bron №"), ("start_date", "Boshlanish"), ("end_date", "Tugash"), ("days", "Kunlar"), ("car", "Avtomobil"),
            ("city", "Shahar"), ("status", "Holat"), ("payment_status", "To'lov"), ("price_per_day", "Kunlik narx"),
            ("delivery", "Yetkazib berish"), ("total_price", "Jami"), ("refunded", "Qaytarilgan")]
    if kind != "renter":
        cols += [("commission", "Komissiya"), ("owner_payout", "Owner ulushi"), ("renter", "Ijarachi")]
    if kind == "admin":
        cols += [("owner", "Owner")]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([tr(h) for _, h in cols])
    labels = {"pending": "Kutilmoqda", "approved": "Tasdiqlangan", "completed": "Yakunlangan", "rejected": "Rad etilgan",
              "cancelled": "Bekor qilingan", "on_site": "Joyida", "paid": "Onlayn to'langan", "refunded": "Qaytarilgan",
              "refund_pending": "Qaytarish kutilmoqda"}
    for it in items:
        it["car"] = car_title(it)
        it["status"], it["payment_status"] = tr(labels[it["status"]]), tr(labels[it["payment_status"]])
        w.writerow([it[k] for k, _ in cols])
    name = f"carrent-{kind}-{start.isoformat()}_{end.isoformat()}.csv"
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


routes = [
    Route("/api/analytics/{kind}.csv", report_csv, methods=["GET"]),
    Route("/api/analytics/{kind}", report, methods=["GET"]),
]
