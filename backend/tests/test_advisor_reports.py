"""Maslahatchi (tavsiya) va hisobotlar (owner, ijarachi, admin, CSV)."""
from datetime import date, timedelta

from starlette.testclient import TestClient

from app.db import get_db
from app.main import app
from conftest import H, make_car, make_user


def d(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


# ---------------- Maslahatchi ----------------
def _fleet():
    owner, _ = make_user()
    city = "Navoiy"   # har test o'z parkini oladi: oldingi testlardagi Navoiy e'lonlari yashiriladi
    with get_db() as db:
        db.execute("UPDATE cars SET is_active = 0 WHERE city = ?", (city,))
    cars = {
        "minivan": make_car(owner, brand="Kia", model="Carnival", body_type="minivan", seats=7, city=city, price_per_day=550_000,
                            features=["ac", "child_seat", "camera"]),
        "hatch": make_car(owner, brand="Chevrolet", model="Spark", body_type="hatchback", seats=4, city=city, price_per_day=200_000,
                          fuel="gas", features=["ac"]),
        "suv": make_car(owner, brand="Toyota", model="Land Cruiser", body_type="suv", seats=5, city=city, price_per_day=900_000,
                        drive="awd", transmission="automatic", features=["ac", "abs", "airbags", "camera"]),
        "manual": make_car(owner, brand="Lada", model="Niva", body_type="suv", seats=4, city=city, price_per_day=250_000,
                           transmission="manual", drive="awd"),
    }
    return owner, city, cars


def advise(client, **body):
    r = client.post("/api/advisor", headers=H, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_family_trip_prefers_minivan_and_respects_seats():
    owner, city, cars = _fleet()
    c = TestClient(app)
    r = advise(c, purpose="family", passengers=6, luggage="large", city=city, features=["child_seat"])
    ids = [x["id"] for x in r["items"]]
    assert ids == [cars["minivan"]["id"]]                                     # 7 o'rindiq — faqat miniven sig'adi
    top = r["items"][0]
    codes = {p["code"] for p in top["pros"]}
    assert {"body_fits", "seats_ok", "has_features"} <= codes and top["badge"] == "best_match"
    assert "tip_child_seat" in r["tips"]


def test_city_budget_economy():
    owner, city, cars = _fleet()
    r = advise(TestClient(app), purpose="city", passengers=2, city=city, budget_max=300_000, priorities=["economy", "price"])
    assert r["items"][0]["id"] == cars["hatch"]["id"]
    assert all(x["price_per_day"] <= 345_000 for x in r["items"])            # byudjet +15% gacha
    assert any(p["code"] == "fuel_cheap" for p in r["items"][0]["pros"])


def test_mountain_new_driver_gets_awd_automatic_first_and_warnings():
    owner, city, cars = _fleet()
    r = advise(TestClient(app), purpose="mountain", passengers=2, city=city, experience="new")
    assert r["items"][0]["id"] == cars["suv"]["id"]
    niva = next(x for x in r["items"] if x["id"] == cars["manual"]["id"])
    assert any(c["code"] == "manual_for_new" for c in niva["cons"])
    assert "tip_awd" in r["tips"] and "tip_new_driver" in r["tips"]


def test_dates_exclude_busy_cars_and_show_total():
    owner, city, cars = _fleet()
    renter, _ = make_user()
    b = renter.post("/api/bookings", headers=H, json={"car_id": cars["hatch"]["id"], "start_date": d(10), "end_date": d(12)}).json()
    owner.post(f"/api/bookings/{b['id']}/approve", headers=H)
    r = advise(TestClient(app), purpose="city", passengers=2, city=city, start_date=d(11), end_date=d(13))
    ids = {x["id"] for x in r["items"]}
    assert cars["hatch"]["id"] not in ids and r["days"] == 3
    assert all(x["total"] == 3 * x["price_per_day"] for x in r["items"])


def test_relaxes_conditions_openly():
    owner, city, cars = _fleet()
    r = advise(TestClient(app), purpose="city", passengers=2, city=city, budget_max=60_000)
    assert "budget" in r["relaxed"] and r["items"]


def test_owner_does_not_see_own_cars_and_validation():
    owner, city, cars = _fleet()
    r = advise(owner, purpose="city", passengers=1, city=city)
    assert not ({x["id"] for x in r["items"]} & {c["id"] for c in cars.values()})
    c = TestClient(app)
    assert c.post("/api/advisor", headers=H, json={"purpose": "city", "start_date": d(1)}).status_code == 422
    assert c.post("/api/advisor", headers=H, json={"purpose": "city", "features": ["jetpack"]}).status_code == 422
    assert c.post("/api/advisor", headers=H, json={"purpose": "city", "priorities": ["economy", "comfort", "safety", "price"]}).status_code == 422
    assert c.post("/api/advisor", json={"purpose": "city"}).status_code == 403   # CSRF sarlavhasiz


# ---------------- Hisobotlar ----------------
def _completed_trip(owner, renter, car, start_days_ago: int, days: int = 2):
    b = renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(3), "end_date": d(3 + days - 1)}).json()
    owner.post(f"/api/bookings/{b['id']}/approve", headers=H)
    s, e = d(-start_days_ago), d(-start_days_ago + days - 1)
    with get_db() as db:   # o'tmishdagi ijara (testda vaqtni orqaga suramiz)
        db.execute("UPDATE bookings SET start_date = ?, end_date = ?, status = 'completed' WHERE id = ?", (s, e, b["id"]))
    return b


def test_owner_report_numbers_and_comparison():
    owner, _ = make_user()
    renter, _ = make_user()
    car = make_car(owner, price_per_day=300_000)
    make_car(owner, model="Idle", price_per_day=300_000)                  # bo'sh turgan ikkinchi mashina
    _completed_trip(owner, renter, car, start_days_ago=5)                  # joriy davr: 600 000
    _completed_trip(owner, renter, car, start_days_ago=40)                 # o'tgan davr: 600 000
    _completed_trip(owner, renter, car, start_days_ago=37)                 # o'tgan davr: 600 000
    r = owner.get(f"/api/analytics/owner?from={d(-29)}&to={d(0)}").json()
    k = {x["code"]: x for x in r["kpis"]}
    assert k["gross"]["value"] == 600_000 and k["gross"]["prev"] == 1_200_000 and k["gross"]["change"] == -50.0
    assert k["income"]["value"] == 540_000 and k["trips"]["value"] == 1
    codes = {i["code"] for i in r["insights"]}
    assert "income_down" in codes and "idle_car" in codes
    assert r["series"]["unit"] == "day" and len(r["series"]["points"]) == 30
    assert sum(p["v"] for p in r["series"]["points"]) == 540_000
    idle = next(c for c in r["tables"]["per_car"] if "Idle" in c["title"])
    assert idle["occupancy"] == 0 and idle["idle_days"] == 30


def test_renter_report_and_privacy():
    owner, _ = make_user()
    renter, _ = make_user()
    car = make_car(owner, price_per_day=250_000)
    _completed_trip(owner, renter, car, start_days_ago=3, days=3)
    r = renter.get(f"/api/analytics/renter?from={d(-29)}&to={d(0)}").json()
    k = {x["code"]: x for x in r["kpis"]}
    assert k["spent"]["value"] == 750_000 and k["rental_days"]["value"] == 3 and k["avg_day"]["value"] == 250_000
    assert r["tables"]["trips"][0]["car_id"] == car["id"]
    assert {i["code"] for i in r["insights"]} >= {"renter_total", "renter_review"}
    other, _ = make_user()
    assert other.get(f"/api/analytics/renter?from={d(-29)}&to={d(0)}").json()["tables"]["trips"] == []
    # owner hisobotida ijarachining shaxsiy hisoboti ko'rinmaydi va aksincha
    assert renter.get(f"/api/analytics/owner?from={d(-29)}&to={d(0)}").json()["tables"]["per_car"] == []


def test_admin_report_and_access():
    admin, _ = make_user("admin")
    user, _ = make_user()
    assert user.get("/api/analytics/admin").status_code == 403
    assert user.get("/api/analytics/admin.csv").status_code == 403
    assert TestClient(app).get("/api/analytics/owner").status_code == 401
    r = admin.get("/api/analytics/admin").json()
    assert {k["code"] for k in r["kpis"]} >= {"gmv", "platform_income", "online_paid", "lost_rate"}
    assert set(r["tables"]) == {"by_city", "top_owners", "top_cars", "providers", "funnel"}
    assert admin.get(f"/api/analytics/admin?from={d(-400)}&to={d(0)}").status_code == 400
    assert user.get("/api/analytics/nope").status_code == 404


def test_csv_export_scoped_and_excel_friendly():
    owner, _ = make_user()
    renter, _ = make_user()
    car = make_car(owner, brand="CsvBrand", price_per_day=300_000)
    _completed_trip(owner, renter, car, start_days_ago=2)
    r = owner.get(f"/api/analytics/owner.csv?from={d(-29)}&to={d(0)}")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.text.startswith("﻿") and "CsvBrand" in r.text and "attachment" in r.headers["content-disposition"]
    rr = renter.get(f"/api/analytics/renter.csv?from={d(-29)}&to={d(0)}").text
    assert "CsvBrand" in rr and "Komissiya" not in rr                       # ijarachiga komissiya ustuni ko'rsatilmaydi
    assert "CsvBrand" not in make_user()[0].get(f"/api/analytics/renter.csv?from={d(-29)}&to={d(0)}").text
