"""Tavsiya etiladigan narx (qoidaviy model) va shaxsiylashtirilgan tavsiyalar (content-based).

Ikkalasi ham faqat bazadagi real ma'lumotlardan hisoblanadi. Ma'lumot kam bo'lsa, natija "ishonch past" deb belgilanadi.
"""
import json
import statistics
from datetime import datetime, timezone

from starlette.requests import Request
from starlette.routing import Route

from ..db import get_db, rows
from ..security import current_user_or_none
from ..utils import ok, q_date, q_int, q_str, today
from .cars import CAR_COLUMNS, PUBLIC_WHERE, serialize

AGE_STEP = 0.03          # har yil farqi uchun ±3%
AGE_CAP = 0.30           # yosh tuzatishining chegarasi
FEATURE_STEP = 0.01      # har bir qulaylik +1%
FEATURE_CAP = 0.08
SEASON = {6: 1.10, 7: 1.12, 8: 1.10, 12: 1.05, 1: 1.05, 3: 1.05}   # yozgi va bayram (Navro'z, Yangi yil) talabi


def _percentile(sorted_vals: list[int], p: float) -> float:
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def _round10k(x: float) -> int:
    return int(round(x / 10_000) * 10_000)


def suggest_price(db, brand: str, model: str, year: int, city: str, body_type: str, n_features: int = 0,
                  exclude_car_id: int | None = None, month: int | None = None) -> dict:
    """O'xshash avtomobillar narxining medianasi + yosh, qulayliklar va mavsum bo'yicha tuzatish."""
    month = month or today().month
    levels = [
        ("same_model_city", "LOWER(c.brand) = LOWER(:brand) AND LOWER(c.model) = LOWER(:model) AND c.city = :city"),
        ("same_model", "LOWER(c.brand) = LOWER(:brand) AND LOWER(c.model) = LOWER(:model)"),
        ("same_body_city", "c.body_type = :body AND c.city = :city"),
        ("same_body", "c.body_type = :body"),
    ]
    params = {"brand": brand, "model": model, "city": city, "body": body_type, "ex": exclude_car_id or 0, "y": year}
    comps, level = [], None
    for name, cond in levels:
        found = rows(db.execute(
            f"""SELECT c.price_per_day AS price, c.year FROM cars c JOIN users u ON u.id = c.owner_id
                WHERE {PUBLIC_WHERE} AND c.id != :ex AND ABS(c.year - :y) <= 6 AND {cond}
                UNION ALL
                SELECT b.price_per_day AS price, c.year FROM bookings b JOIN cars c ON c.id = b.car_id
                WHERE b.status IN ('approved', 'completed') AND b.start_date >= date('now', '-90 days')
                AND c.id != :ex AND ABS(c.year - :y) <= 6 AND {cond}""", params))
        if len(found) >= 4:
            comps, level = found, name
            break
        if found and not comps:
            comps, level = found, name
    if not comps:
        return {"suggested": None, "low": None, "high": None, "confidence": "none", "n": 0, "factors": []}

    adjusted = sorted(
        c["price"] * (1 + max(-AGE_CAP, min(AGE_CAP, AGE_STEP * (year - c["year"])))) for c in comps)
    med, p25, p75 = statistics.median(adjusted), _percentile(adjusted, 0.25), _percentile(adjusted, 0.75)
    feat = min(FEATURE_CAP, FEATURE_STEP * n_features)
    season = SEASON.get(month, 1.0)
    k = (1 + feat) * season
    n = len(comps)
    confidence = "high" if n >= 10 and level.startswith("same_model") else "medium" if n >= 4 else "low"
    spread = max(p75 - p25, med * 0.1)
    return {
        "suggested": _round10k(med * k),
        "low": _round10k((med - spread / 2) * k),
        "high": _round10k((med + spread / 2) * k),
        "confidence": confidence, "n": n, "level": level,
        "factors": [f for f in [
            {"code": "comparables", "n": n, "level": level},
            {"code": "age_adjusted"},
            {"code": "features", "pct": round(feat * 100)} if feat else None,
            {"code": "season", "pct": round((season - 1) * 100)} if season != 1.0 else None,
        ] if f],
    }


async def pricing_suggest(request: Request):
    year = q_int(request, "year", today().year - 3, lo=1990, hi=today().year + 1)
    feats = [f for f in (q_str(request, "features", 300) or "").split(",") if f]
    with get_db() as db:
        result = suggest_price(db, q_str(request, "brand") or "", q_str(request, "model") or "", year,
                               q_str(request, "city") or "", q_str(request, "body_type") or "sedan", len(feats),
                               q_int(request, "exclude"))
    return ok(result)


# ---------------- Tavsiyalar ----------------
W = {"budget": 0.30, "city": 0.20, "similar": 0.20, "rating": 0.15, "popular": 0.10, "fresh": 0.05}
BAYES_C = 5


def _days_ago(ts: str) -> float:
    try:
        return (datetime.now(timezone.utc).replace(tzinfo=None) - datetime.fromisoformat(ts.replace(" ", "T")[:19])).days
    except ValueError:
        return 999


def recommend(db, user: dict | None, limit: int = 8, start=None, end=None) -> list[dict]:
    uid = user["id"] if user else 0
    # Foydalanuvchi profili: faqat sevimlilar va bronlar (xususiy xabarlar ishlatilmaydi)
    history = rows(db.execute(
        """SELECT c.price_per_day, c.body_type, c.city, c.brand FROM favorites f JOIN cars c ON c.id = f.car_id WHERE f.user_id = :u
           UNION ALL
           SELECT c.price_per_day, c.body_type, c.city, c.brand FROM bookings b JOIN cars c ON c.id = b.car_id
           WHERE b.renter_id = :u AND b.status IN ('approved', 'completed', 'pending')""", {"u": uid}))
    budget = statistics.median([h["price_per_day"] for h in history]) if history else None
    cities = [h["city"] for h in history] + ([user["region"]] if user and user.get("region") else [])
    fav_city = max(set(cities), key=cities.count) if cities else None
    bodies = {h["body_type"] for h in history}
    brands = {h["brand"] for h in history}

    where, params = [PUBLIC_WHERE, "c.owner_id != ?"], [uid]
    if start and end:
        where.append("""NOT EXISTS (SELECT 1 FROM bookings b WHERE b.car_id = c.id AND b.status IN ('approved', 'pending')
                        AND b.start_date <= ? AND b.end_date >= ?)
                        AND NOT EXISTS (SELECT 1 FROM car_blocks k WHERE k.car_id = c.id AND k.start_date <= ? AND k.end_date >= ?)""")
        params += [end.isoformat(), start.isoformat(), end.isoformat(), start.isoformat()]
    cands = [serialize(c) for c in rows(db.execute(
        f"SELECT {CAR_COLUMNS} FROM cars c JOIN users u ON u.id = c.owner_id WHERE {' AND '.join(where)}", params))]
    if not cands:
        return []
    m = db.execute("SELECT AVG(rating) FROM reviews WHERE kind = 'car'").fetchone()[0] or 4.0
    max_views = max(c["views"] for c in cands) or 1

    for c in cands:
        n, r = c["reviews_count"], c["rating"] or 0
        bayes = (BAYES_C * m + r * n) / (BAYES_C + n)
        s = {
            "budget": (1.0 if 0.7 * budget <= c["price_per_day"] <= 1.3 * budget
                       else max(0.0, 1 - abs(c["price_per_day"] - budget) / budget)) if budget else 0.5,
            "city": (1.0 if c["city"] == fav_city else 0.0) if fav_city else 0.5,
            "similar": (0.6 * (c["body_type"] in bodies) + 0.4 * (c["brand"] in brands)) if history else 0.0,
            "rating": (bayes - 1) / 4,
            "popular": c["views"] / max_views,
            "fresh": max(0.0, 1 - _days_ago(c["created_at"]) / 60),
        }
        c["score"] = round(sum(W[k] * v for k, v in s.items()), 4)
        # Sabab (frontend tarjima qiladi)
        if history and s["budget"] >= 0.9 and s["city"] == 1.0:
            c["reason"] = "budget_city"
        elif history and s["similar"] >= 0.6:
            c["reason"] = "similar"
        elif s["fresh"] >= 0.75:
            c["reason"] = "new"
        elif n >= 2 and bayes >= 4.3:
            c["reason"] = "top_rated"
        else:
            c["reason"] = "popular"

    cands.sort(key=lambda c: c["score"], reverse=True)
    picked, per_model = [], {}
    for c in cands:  # xilma-xillik: bir modeldan ko'pi bilan 2 ta
        key = (c["brand"], c["model"])
        if per_model.get(key, 0) >= 2:
            continue
        per_model[key] = per_model.get(key, 0) + 1
        picked.append(c)
        if len(picked) >= limit:
            break
    # Yangi e'longa imkoniyat: 6 tadan birida yangi e'lon bo'lmasa, oxirgisini almashtiramiz
    fresh = [c for c in cands if _days_ago(c["created_at"]) <= 14 and c not in picked]
    if len(picked) >= 6 and fresh and not any(_days_ago(c["created_at"]) <= 14 for c in picked[:6]):
        fresh[0]["reason"] = "new"
        picked[5] = fresh[0]
    return picked


async def recommendations(request: Request):
    user = current_user_or_none(request)
    with get_db() as db:
        items = recommend(db, user, q_int(request, "limit", 8, lo=1, hi=24), q_date(request, "start"), q_date(request, "end"))
    return ok({"items": items, "personal": bool(user)})


routes = [
    Route("/api/pricing/suggest", pricing_suggest, methods=["GET"]),
    Route("/api/recommendations", recommendations, methods=["GET"]),
]
