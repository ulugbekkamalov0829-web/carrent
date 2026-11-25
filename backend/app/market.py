"""v10: daromad va ishonch vositalari (Turo / Getaround / Airbnb tajribasi asosida).

KAFOLAT REJASI (protection plan) — ijarachi bron paytida tanlaydi:
  * "none"     — qo'shimcha to'lov yo'q; shikast bo'lsa ijarachi ta'mir narxini to'liq qoplaydi (depozit + qolgani).
  * "standard" — ijara narxining 10%; shikast bo'lsa ijarachi ko'pi bilan liability_cap so'm to'laydi, qolganini platforma
                  kafolat jamg'armasi qoplaydi.
  * "premium"  — ijara narxining 18%; javobgarlik chegarasi juda kichik.
  Bu sug'urta emas (sug'urta litsenziyasi kerak), balki platformaning "javobgarlikni cheklash" xizmati — to'lov to'liq
  platforma daromadiga tushadi va jamg'arma shu puldan to'ldiriladi. Haqiqiy ishga tushirishda sug'urta kompaniyasi bilan
  hamkorlik (masalan KASKO / OSAGO qo'shimchasi) tavsiya qilinadi.

QO'SHIMCHA XIZMATLAR (extras) — owner narxini belgilaydi (0/yo'q = taklif qilinmaydi): bolalar o'rindig'i, oldindan
  to'langan yoqilg'i, tozalash, cheksiz probeg, haydovchi bilan. Platforma ulushi EXTRAS_FEE_PCT.

PROMOKOD — admin yaratadi; chegirma platforma ulushidan beriladi (owner daromadi kamaymaydi).
"""
import json

from .db import get_setting, one

EXTRAS = {             # kod -> hisoblash birligi
    "child_seat": "day",
    "prepaid_fuel": "trip",
    "cleaning": "trip",
    "unlimited_km": "day",
    "driver": "day",
}
EXTRAS_FEE_PCT = 10

DEFAULT_PLANS = {
    "none": {"pct": 0, "cap": None},
    "standard": {"pct": 10, "cap": 3_000_000},
    "premium": {"pct": 18, "cap": 500_000},
}


def plans(db) -> dict:
    """Admin sozlamalarda o'zgartirishi mumkin (protection_plans JSON); bo'lmasa standart qiymatlar."""
    raw = get_setting(db, "protection_plans", "")
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        data = {}
    out = {}
    for code, d in DEFAULT_PLANS.items():
        x = data.get(code) or {}
        out[code] = {"pct": int(x.get("pct", d["pct"])), "cap": x.get("cap", d["cap"])}
    out["none"] = {"pct": 0, "cap": None}
    return out


def car_extras(car: dict) -> dict:
    raw = car.get("extras") or "{}"
    data = json.loads(raw) if isinstance(raw, str) else dict(raw)
    return {k: int(v) for k, v in data.items() if k in EXTRAS and int(v or 0) > 0}


def extras_lines(car: dict, chosen: list[str], days: int) -> list[dict]:
    offered = car_extras(car)
    lines = []
    for code in dict.fromkeys(chosen or []):
        if code not in offered:
            continue
        if code == "unlimited_km" and not car.get("km_limit"):
            continue
        unit = EXTRAS[code]
        amount = offered[code] * (days if unit == "day" else 1)
        lines.append({"code": code, "unit": unit, "price": offered[code], "amount": amount})
    return lines


def find_promo(db, code: str | None, uid: int | None) -> tuple[dict | None, str | None]:
    """(promo, xato_kodi). Xato kodlari: not_found, expired, used_up, used_by_you."""
    if not code:
        return None, None
    p = one(db.execute("SELECT * FROM promo_codes WHERE code = ? COLLATE NOCASE AND is_active = 1", (code.strip(),)))
    if not p:
        return None, "not_found"
    if p["expires_on"] and p["expires_on"] < db.execute("SELECT date('now')").fetchone()[0]:
        return None, "expired"
    used = db.execute("SELECT COUNT(*) FROM bookings WHERE promo_code = ? COLLATE NOCASE AND status NOT IN ('rejected', 'cancelled')",
                      (p["code"],)).fetchone()[0]
    if p["max_uses"] and used >= p["max_uses"]:
        return None, "used_up"
    if uid and db.execute("SELECT 1 FROM bookings WHERE promo_code = ? COLLATE NOCASE AND renter_id = ? "
                          "AND status NOT IN ('rejected', 'cancelled')", (p["code"], uid)).fetchone():
        return None, "used_by_you"
    return p, None


def owner_stats(db, owner_id: int) -> dict:
    """Javob berish ko'rsatkichi (Airbnb/Getaround uslubida): so'rovlarning necha foiziga javob bergan, o'rtacha necha soatda,
    necha foizini qabul qilgan. Avtomatik muddati o'tganlar (javobsiz) ham hisobga kiradi."""
    r = db.execute(
        """SELECT COUNT(*) AS total,
                  SUM(CASE WHEN b.responded_at IS NOT NULL OR b.status IN ('approved', 'completed') THEN 1 ELSE 0 END) AS answered,
                  SUM(CASE WHEN b.status IN ('approved', 'completed') THEN 1 ELSE 0 END) AS accepted,
                  AVG(CASE WHEN b.responded_at IS NOT NULL AND b.instant = 0
                      THEN (julianday(b.responded_at) - julianday(b.created_at)) * 24 END) AS hours
           FROM bookings b JOIN cars c ON c.id = b.car_id
           WHERE c.owner_id = ? AND b.status != 'cancelled' AND b.created_at >= datetime('now', '-180 days')""",
        (owner_id,)).fetchone()
    total = r["total"] or 0
    if not total:
        return {"requests": 0, "response_rate": None, "acceptance_rate": None, "response_hours": None, "trusted": False}
    rate = round(100 * (r["answered"] or 0) / total)
    acc = round(100 * (r["accepted"] or 0) / total)
    hours = round(r["hours"], 1) if r["hours"] is not None else None
    return {"requests": total, "response_rate": rate, "acceptance_rate": acc, "response_hours": hours,
            "trusted": total >= 3 and rate >= 90 and (hours is None or hours <= 6)}
