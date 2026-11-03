"""Maslahatchi: ijarachi xohishlarini kiritadi (maqsad, yo'lovchilar, yuk, byudjet, sana, ustuvorliklar),
tizim har bir avtomobilga 0–100 moslik balli beradi va NEGA mos ekanini (va nimasi mos emasligini) tushuntiradi.

Qoidaga asoslangan, shaffof model — "qora quti" yo'q:
  1) Qat'iy shartlar: o'rindiq yetarli, tanlangan sanalarda bo'sh, ijara muddati e'lon chegarasida, kerak bo'lsa yetkazib berish,
     tanlangan uzatma, shahar, byudjet (+15% gacha). Natija bo'lmasa shartlar bosqichma-bosqich yumshatiladi va bu ochiq aytiladi.
  2) Ball: maqsadga mos kuzov, byudjet, joy (yo'lovchi + yuk), sharhlar (Bayes o'rtachasi), so'ralgan qulayliklar,
     tanlangan ustuvorliklar (tejamkorlik, qulaylik, xavfsizlik, nufuz, arzonlik) va haydovchi tajribasi.
  3) Har bir avtomobil uchun ijobiy sabablar va ogohlantirishlar kod + parametr ko'rinishida qaytadi (frontend uch tilda yozadi).
"""
from starlette.requests import Request
from starlette.routing import Route

from ..db import get_db, rows
from ..schemas import AdvisorIn
from ..security import current_user_or_none
from ..utils import ok, parse_body
from .cars import CAR_COLUMNS, PUBLIC_WHERE, serialize

# Maqsad -> kuzov turi qanchalik mos (0..1)
PURPOSE_BODY = {
    "city":     {"hatchback": 1.0, "sedan": 0.9, "crossover": 0.75, "coupe": 0.65, "suv": 0.5, "minivan": 0.35, "pickup": 0.25},
    "family":   {"minivan": 1.0, "suv": 0.9, "crossover": 0.85, "sedan": 0.65, "hatchback": 0.45, "pickup": 0.35, "coupe": 0.15},
    "trip":     {"crossover": 0.95, "sedan": 0.9, "suv": 0.9, "minivan": 0.8, "hatchback": 0.6, "pickup": 0.55, "coupe": 0.5},
    "mountain": {"suv": 1.0, "pickup": 0.9, "crossover": 0.75, "minivan": 0.4, "sedan": 0.3, "hatchback": 0.25, "coupe": 0.1},
    "business": {"sedan": 1.0, "suv": 0.85, "crossover": 0.75, "coupe": 0.75, "minivan": 0.5, "hatchback": 0.45, "pickup": 0.25},
    "event":    {"sedan": 0.95, "coupe": 0.95, "suv": 0.9, "crossover": 0.7, "minivan": 0.6, "hatchback": 0.4, "pickup": 0.3},
    "cargo":    {"pickup": 1.0, "minivan": 0.95, "suv": 0.7, "crossover": 0.55, "hatchback": 0.35, "sedan": 0.3, "coupe": 0.05},
}
LUGGAGE_NEED = {"none": 0, "small": 1, "medium": 2, "large": 3}
BODY_LUGGAGE = {"coupe": 0, "hatchback": 1, "sedan": 2, "crossover": 2, "suv": 3, "minivan": 3, "pickup": 3}
FUEL_ECONOMY = {"electric": 1.0, "hybrid": 0.95, "gas": 0.85, "diesel": 0.7, "petrol": 0.5}
COMFORT_FEATS = {"ac", "cruise", "heated_seats", "leather", "carplay", "sunroof", "navigation", "bluetooth"}
SAFETY_FEATS = {"abs", "airbags", "camera", "parking_sensors"}
PREMIUM_BRANDS = {"mercedes-benz", "mercedes", "bmw", "lexus", "audi", "genesis", "porsche", "land rover", "range rover", "volvo", "infiniti"}
# Narx (price) har doim hisobga olinadi: bir xil darajada mos keladiganlardan arzonrog'i yuqorida — ko'proq odam bron qiladi
BASE_W = {"purpose": 0.25, "budget": 0.19, "space": 0.13, "rating": 0.09, "features": 0.09, "economy": 0.05,
          "comfort": 0.04, "safety": 0.04, "prestige": 0.0, "experience": 0.05, "price": 0.10}
CRITICAL = {"body_weak", "manual_for_new", "over_budget", "luggage_small", "awd_no"}
PRIORITY_BOOST = 0.14
BAYES_C, BAYES_M = 5, 4.2
TIPS = {"city": ["tip_city_compact", "tip_fuel_gas"], "family": ["tip_child_seat", "tip_luggage"], "trip": ["tip_km_limit", "tip_fuel_gas"],
        "mountain": ["tip_awd", "tip_clearance"], "business": ["tip_clean_sedan"], "event": ["tip_book_early"], "cargo": ["tip_cargo_size"]}


def _norm(score_parts: dict, w: dict) -> float:
    total_w = sum(w.values()) or 1
    return sum(w[k] * score_parts.get(k, 0) for k in w) / total_w


def _candidates(db, data: AdvisorIn, uid: int, relax: set) -> list[dict]:
    where, params = [PUBLIC_WHERE, "c.owner_id != ?", "c.seats >= ?"], [uid, data.passengers]
    if data.start_date:
        s, e = data.start_date.isoformat(), data.end_date.isoformat()
        days = (data.end_date - data.start_date).days + 1
        where.append("""NOT EXISTS (SELECT 1 FROM bookings b WHERE b.car_id = c.id AND b.status IN ('approved', 'pending')
                        AND b.start_date <= ? AND b.end_date >= ?)
                        AND NOT EXISTS (SELECT 1 FROM car_blocks k WHERE k.car_id = c.id AND k.start_date <= ? AND k.end_date >= ?)
                        AND c.min_days <= ? AND c.max_days >= ?""")
        params += [e, s, e, s, days, days]
    if data.delivery:
        where.append("c.delivery_price IS NOT NULL")
    if data.transmission and "transmission" not in relax:
        where.append("c.transmission = ?"); params.append(data.transmission)
    if data.city and "city" not in relax:
        where.append("c.city = ?"); params.append(data.city)
    if data.budget_max and "budget" not in relax:
        where.append("c.price_per_day <= ?"); params.append(int(data.budget_max * 1.15))
    return [serialize(c) for c in rows(db.execute(
        f"SELECT {CAR_COLUMNS} FROM cars c JOIN users u ON u.id = c.owner_id WHERE {' AND '.join(where)}", params))]


def score_car(c: dict, data: AdvisorIn, newest_year: int, prange: tuple[int, int] = (0, 0), market: dict | None = None) -> dict:
    feats = set(c["features"])
    pros, cons = [], []
    body_fit = PURPOSE_BODY[data.purpose].get(c["body_type"], 0.4)
    awd = c.get("drive") == "awd"
    if data.purpose == "mountain" and awd:
        body_fit = min(1.0, body_fit + 0.25)
    parts = {"purpose": body_fit}
    if body_fit >= 0.85:
        pros.append({"code": "body_fits", "p": {"body": c["body_type"], "purpose": data.purpose}})
    elif body_fit < 0.5:
        cons.append({"code": "body_weak", "p": {"body": c["body_type"], "purpose": data.purpose}})
    if data.purpose == "mountain":
        (pros if awd else cons).append({"code": "awd_yes" if awd else "awd_no"})

    # Byudjet: byudjet ichida — to'liq ball (arzonroq bo'lsa biroz ko'proq), oshsa — tez kamayadi
    price = c["price_per_day"]
    if data.budget_max:
        if price <= data.budget_max:
            parts["budget"] = 0.85 + 0.15 * (1 - price / data.budget_max)
            pros.append({"code": "in_budget", "p": {"price": price, "left": data.budget_max - price}})
        else:
            parts["budget"] = max(0.0, 1 - (price - data.budget_max) / (0.3 * data.budget_max))
            cons.append({"code": "over_budget", "p": {"over": price - data.budget_max}})
    else:
        parts["budget"] = 0.6

    # Joy: yo'lovchilar uchun zaxira o'rindiq va yuk sig'imi
    spare = c["seats"] - data.passengers
    lug_gap = BODY_LUGGAGE.get(c["body_type"], 1) - LUGGAGE_NEED[data.luggage]
    parts["space"] = max(0.0, min(1.0, 0.6 + 0.2 * min(spare, 2) + 0.2 * lug_gap))
    if spare >= 1 and data.passengers >= 3:
        pros.append({"code": "seats_ok", "p": {"seats": c["seats"], "n": data.passengers}})
    if lug_gap >= 0 and data.luggage in ("medium", "large"):
        pros.append({"code": "luggage_ok"})
    elif lug_gap < 0:
        cons.append({"code": "luggage_small"})

    n, r = c["reviews_count"], c["rating"] or 0
    bayes = (BAYES_C * BAYES_M + r * n) / (BAYES_C + n)
    parts["rating"] = (bayes - 1) / 4
    if n >= 2 and r >= 4.5:
        pros.append({"code": "top_rated", "p": {"rating": r, "n": n}})
    elif n >= 2 and r < 3.8:
        cons.append({"code": "low_rating", "p": {"rating": r}})

    want = set(data.features)
    if want:
        have = want & feats
        parts["features"] = len(have) / len(want)
        if have:
            pros.append({"code": "has_features", "p": {"list": sorted(have)}})
        if want - have:
            cons.append({"code": "missing_features", "p": {"list": sorted(want - have)}})
    else:
        parts["features"] = min(1.0, len(feats) / 8)

    eco = FUEL_ECONOMY.get(c["fuel"], 0.5)
    if c.get("engine_l"):
        eco = max(0.0, min(1.0, eco + (1.6 - c["engine_l"]) * 0.12))
    parts["economy"] = eco
    if c["fuel"] in ("electric", "hybrid", "gas") and ("economy" in data.priorities or data.purpose in ("city", "trip")):
        pros.append({"code": "fuel_cheap", "p": {"fuel": c["fuel"]}})
    age = max(0, newest_year - c["year"])
    parts["comfort"] = min(1.0, 0.5 * len(feats & COMFORT_FEATS) / 4 + 0.5 * max(0.0, 1 - age / 10))
    parts["safety"] = min(1.0, 0.6 * len(feats & SAFETY_FEATS) / 3 + 0.4 * max(0.0, 1 - age / 12))
    premium = c["brand"].lower() in PREMIUM_BRANDS
    parts["prestige"] = min(1.0, (0.6 if premium else 0.15) + 0.25 * max(0.0, 1 - age / 6) + (0.15 if "leather" in feats else 0))
    # Narx bahosi nomzodlar orasida nisbiy: eng arzoni 1, eng qimmati 0 (mutlaq chegara emas)
    lo, hi = prange
    parts["price"] = 1.0 if hi <= lo else max(0.0, min(1.0, (hi - price) / (hi - lo)))
    avg = (market or {}).get(c["body_type"])
    if avg and price <= avg * 0.95:
        pros.insert(0, {"code": "below_market", "p": {"pct": round(100 * (avg - price) / avg)}})
    elif hi > lo and parts["price"] >= 0.85:
        pros.insert(0, {"code": "cheapest_city"})
    if "comfort" in data.priorities and parts["comfort"] >= 0.7:
        pros.append({"code": "comfortable"})
    if "safety" in data.priorities and len(feats & SAFETY_FEATS) >= 2:
        pros.append({"code": "safe", "p": {"list": sorted(feats & SAFETY_FEATS)}})
    if "prestige" in data.priorities and parts["prestige"] >= 0.65:
        pros.append({"code": "prestige"})
    if age <= 2:
        pros.append({"code": "new_car", "p": {"year": c["year"]}})

    exp = 0.6
    if data.experience == "new":
        exp = (0.5 if c["transmission"] == "automatic" else 0.0) + (0.25 if feats & {"camera", "parking_sensors"} else 0) \
              + (0.25 if c["body_type"] in ("hatchback", "sedan", "crossover") else 0.05)
        if c["transmission"] == "automatic":
            pros.append({"code": "easy_for_new"})
        else:
            cons.append({"code": "manual_for_new"})
        if c["deposit"] >= 1_000_000:
            cons.append({"code": "high_deposit", "p": {"deposit": c["deposit"]}})
    parts["experience"] = exp
    if c.get("km_limit") and data.purpose == "trip":
        cons.append({"code": "km_limit", "p": {"km": c["km_limit"]}})

    w = dict(BASE_W)
    for pr in data.priorities:
        w[pr] = w.get(pr, 0) + PRIORITY_BOOST
    if data.experience == "new":
        w["experience"] += 0.08
    match = round(100 * _norm(parts, w))
    return {"match": max(1, min(99, match)), "pros": pros[:5], "cons": cons[:3], "parts": {k: round(v, 2) for k, v in parts.items()}}


async def advise(request: Request):
    data = await parse_body(request, AdvisorIn)
    user = current_user_or_none(request)
    uid = user["id"] if user else 0
    days = (data.end_date - data.start_date).days + 1 if data.start_date else None
    # Faqat foydalanuvchi kiritgan shartlar yumshatiladi, tartib: shahar -> byudjet -> uzatma
    given = [k for k, v in (("city", data.city), ("budget", data.budget_max), ("transmission", data.transmission)) if v]
    relax_steps = [set(given[:i]) for i in range(len(given) + 1)]
    with get_db() as db:
        relaxed, cands = set(), []
        for step in relax_steps:
            cands = _candidates(db, data, uid, step)
            if cands:
                relaxed = step
                break
        # Tanlangan shaharda variant kam bo'lsa — boshqa shaharlardagilarni ham qo'shamiz ("boshqa shaharda" deb belgilanadi)
        if 0 < len(cands) < 3 and "city" in given and "city" not in relaxed:
            have = {c["id"] for c in cands}
            cands += [c for c in _candidates(db, data, uid, relaxed | {"city"}) if c["id"] not in have]
        newest = max([c["year"] for c in cands], default=0)
        prices = [c["price_per_day"] for c in cands]
        prange = (min(prices, default=0), max(prices, default=0))
        market = {k: v for k, v in db.execute(f"SELECT c.body_type, AVG(c.price_per_day) FROM cars c JOIN users u ON u.id = c.owner_id "
                                              f"WHERE {PUBLIC_WHERE} GROUP BY c.body_type")}
        for c in cands:
            c.update(score_car(c, data, newest, prange, market))
            if days:
                c["total"] = days * c["price_per_day"] + ((c["delivery_price"] or 0) if data.delivery else 0)
            if data.district and c.get("district") == data.district:
                c["pros"].insert(0, {"code": "same_district", "p": {"district": c["district"]}})
                c["match"] = min(99, c["match"] + 4)     # o'z tumaningizda — olib ketish oson
            if data.city and c["city"] != data.city:
                c["cons"].insert(0, {"code": "other_city", "p": {"city": c["city"]}})
                c["match"] = max(1, c["match"] - 12)     # boshqa shaharga borish noqulay — o'z shahringizdagisi oldinda
        # Moslik deyarli teng (2 ball ichida) va jiddiy kamchiligi yo'q bo'lsa — arzonrog'i oldinda
        crit = lambda c: any(x["code"] in CRITICAL for x in c["cons"])
        cands.sort(key=lambda c: (crit(c), -(c["match"] // 2), c["price_per_day"], -c["match"]))
        top = cands[:6]
        # Eng arzon mos variant: eng mosidan 12 balldan ko'p past bo'lmagan eng arzon mashina (ro'yxatda bo'lmasa qo'shiladi)
        cheapest, saving = None, None
        if top:
            ok_ = [c for c in cands if c["match"] >= max(45, top[0]["match"] - 12)
                   and not any(x["code"] in CRITICAL for x in c["cons"])]
            ch = min(ok_, key=lambda c: c["price_per_day"]) if ok_ else None
            if ch and ch["price_per_day"] < top[0]["price_per_day"]:
                cheapest = ch["id"]
                saving = {"per_day": top[0]["price_per_day"] - ch["price_per_day"],
                          "total": (top[0]["price_per_day"] - ch["price_per_day"]) * days if days else None}
                if ch not in top:
                    top = top[:5] + [ch]
        # Belgilar: eng mos, eng arzon, eng tejamkor (bir xil avtomobilga takror berilmaydi)
        badges = {}
        if top:
            badges[top[0]["id"]] = "best_match"
            cheap = min(top, key=lambda c: c["price_per_day"])
            badges.setdefault(cheap["id"], "best_price")
            eco = max(top, key=lambda c: c["parts"]["economy"])
            badges.setdefault(eco["id"], "best_economy")
        if cheapest:
            badges[cheapest] = "best_price" if badges.get(cheapest) in (None, "best_price", "best_economy") else badges[cheapest]
        for c in top:
            c["badge"] = badges.get(c["id"])
            c["market_avg"] = round(market[c["body_type"]]) if market.get(c["body_type"]) else None
            c.pop("description", None)
        # Tejash maslahatlari: aniq raqamlar bilan
        save_tips = []
        if data.delivery:
            dl = max([c["delivery_price"] or 0 for c in top], default=0)
            if dl:
                save_tips.append({"code": "save_nodelivery", "p": {"sum": dl}})
        if data.budget_max and top:
            lower = int(data.budget_max * 0.8 // 10_000 * 10_000)
            n = sum(1 for c in cands if c["price_per_day"] <= lower and c["match"] >= 50)
            if n:
                save_tips.append({"code": "save_budget", "p": {"sum": lower, "n": n}})
        if not any(c["fuel"] in ("gas", "hybrid", "electric") for c in top[:1]) and any(c["fuel"] in ("gas", "hybrid") for c in cands):
            save_tips.append({"code": "save_gas"})
        save_tips += [{"code": "save_compare"}, {"code": "save_deposit"}]
    return ok({"items": top, "total_found": len(cands), "relaxed": sorted(relaxed), "days": days,
               "cheapest_id": cheapest, "saving": saving, "save_tips": save_tips if cands else [],
               "tips": TIPS[data.purpose] + (["tip_new_driver"] if data.experience == "new" else []) +
                       (["tip_dates"] if not data.start_date else [])})


routes = [Route("/api/advisor", advise, methods=["POST"])]
