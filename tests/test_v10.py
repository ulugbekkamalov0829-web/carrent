"""v10: kafolat rejasi, qo'shimcha xizmatlar, promokod, darhol bron, owner javob ko'rsatkichi, jarimalar."""
from datetime import date, timedelta

from app.db import get_db
from conftest import H, make_car, make_user
from test_v7 import verify_docs


def d(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


def test_quote_with_extras_protection_and_money_invariant():
    owner, _ = make_user()
    car = make_car(owner, price_per_day=200000, delivery_price=None, km_limit=300,
                   extras={"child_seat": 30000, "cleaning": 50000, "unlimited_km": 40000})
    assert car["extras"] == {"child_seat": 30000, "cleaning": 50000, "unlimited_km": 40000}
    renter, _ = make_user()
    q = renter.get(f"/api/cars/{car['id']}/quote", params={"start": d(3), "end": d(5), "extras": "child_seat,cleaning,driver",
                                                            "protection": "standard"}).json()
    # 3 kun × 200 000 = 600 000; o'rindiq 3×30 000 = 90 000; tozalash 50 000; haydovchi taklif qilinmagan -> e'tiborsiz
    assert q["rent"] == 600000 and q["extras_total"] == 140000 and [x["code"] for x in q["extras"]] == ["child_seat", "cleaning"]
    assert q["protection_fee"] == 60000 and q["liability_cap"] == 3_000_000
    assert q["total"] == 600000 + 140000 + 60000
    # owner ulushi: ijara − 10% komissiya + xizmatlar − 10%; kafolat to'lovi to'liq platformaga
    assert q["owner_payout"] == 600000 - 60000 + 140000 - 14000
    assert q["commission"] + q["owner_payout"] == q["total"]
    b = renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(3), "end_date": d(5),
                                                      "extras": ["child_seat", "cleaning"], "protection": "premium"})
    assert b.status_code == 201, b.text
    j = b.json()
    assert j["protection"] == "premium" and j["protection_fee"] == 108000 and j["liability_cap"] == 500_000
    assert j["commission"] + j["owner_payout"] == j["total_price"]


def test_promo_code_from_platform_share_once_per_user():
    admin, _ = make_user("admin")
    r = admin.post("/api/admin/promos", headers=H, json={"code": "bahor27", "pct": 50, "max_uses": 5})
    assert r.status_code == 201, r.text
    assert r.json()["items"][0]["code"] == "BAHOR27"
    owner, _ = make_user()
    car = make_car(owner, price_per_day=100000, delivery_price=None)
    renter, _ = make_user()
    q = renter.get(f"/api/cars/{car['id']}/quote", params={"start": d(2), "end": d(3), "promo": "Bahor27"}).json()
    # 50% × 200 000 = 100 000, lekin platforma ulushidan (20 000) oshmaydi -> owner daromadi o'zgarmaydi
    assert q["promo_discount"] == 20000 and q["owner_payout"] == 180000 and q["commission"] == 0
    b = renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(2), "end_date": d(3), "promo": "bahor27"})
    assert b.status_code == 201, b.text
    assert b.json()["promo_discount"] == 20000 and b.json()["total_price"] == 180000
    again = renter.get(f"/api/cars/{car['id']}/quote", params={"start": d(10), "end": d(11), "promo": "BAHOR27"}).json()
    assert again["promo_discount"] == 0 and again["promo_error"]
    bad = renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(10), "end_date": d(11), "promo": "YOQ"})
    assert bad.status_code == 400
    assert admin.get("/api/admin/promos").json()["items"][0]["used"] == 1


def test_instant_book_only_for_verified_renters():
    admin, _ = make_user("admin")
    owner, _ = make_user()
    car = make_car(owner, instant_book=True)
    assert car["instant_book"] is True
    plain, _ = make_user()
    b = plain.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(2), "end_date": d(3)})
    assert b.json()["status"] == "pending" and not b.json()["instant"]
    vip, _ = make_user()
    verify_docs(vip, admin)
    b = vip.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(6), "end_date": d(7)})
    assert b.status_code == 201, b.text
    assert b.json()["status"] == "approved" and b.json()["instant"] == 1 and b.json()["contract_id"]


def test_owner_response_stats_on_car_page():
    owner, _ = make_user()
    car = make_car(owner)
    for i in range(3):
        r, _ = make_user()
        bid = r.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(2 + i * 3), "end_date": d(3 + i * 3)}).json()["id"]
        owner.post(f"/api/bookings/{bid}/approve", headers=H)
    o = make_user()[0].get(f"/api/cars/{car['id']}").json()["owner"]
    assert o["requests"] == 3 and o["response_rate"] == 100 and o["acceptance_rate"] == 100 and o["trusted"] is True


def test_fines_flow_and_period_check():
    owner, _ = make_user()
    car = make_car(owner)
    renter, _ = make_user()
    bid = renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(1), "end_date": d(2)}).json()["id"]
    owner.post(f"/api/bookings/{bid}/approve", headers=H)
    # Ijarani o'tmishga surib "yakunlangan" qilamiz
    with get_db() as db:
        db.execute("UPDATE bookings SET start_date = ?, end_date = ?, status = 'completed' WHERE id = ?", (d(-5), d(-3), bid))
    assert renter.post(f"/api/bookings/{bid}/fines", headers=H, json={"happened_at": d(-4) + " 10:00", "amount": 375000}).status_code == 403
    out = owner.post(f"/api/bookings/{bid}/fines", headers=H, json={"happened_at": d(-10) + " 10:00", "amount": 375000})
    assert out.status_code == 400
    f = owner.post(f"/api/bookings/{bid}/fines", headers=H, json={"happened_at": d(-4) + " 10:15", "amount": 375000, "protocol": "RR1234567"})
    assert f.status_code == 201, f.text
    fid = f.json()["id"]
    assert owner.post(f"/api/bookings/{bid}/fines", headers=H,
                      json={"happened_at": d(-4) + " 11:00", "amount": 100000, "protocol": "RR1234567"}).status_code == 409
    mine = renter.get("/api/my/fines").json()["items"]
    assert len(mine) == 1 and mine[0]["status"] == "open"
    assert any(n["type"] == "fine_new" for n in renter.get("/api/notifications").json()["items"])
    assert owner.post(f"/api/fines/{fid}", headers=H, json={"action": "dispute"}).status_code == 400   # faqat ijarachi
    assert renter.post(f"/api/fines/{fid}", headers=H, json={"action": "dispute"}).json()["status"] == "disputed"
    assert renter.post(f"/api/fines/{fid}", headers=H, json={"action": "paid"}).json()["status"] == "paid"


def test_contract_mentions_protection_and_fines():
    owner, _ = make_user()
    car = make_car(owner, extras={"child_seat": 25000})
    renter, _ = make_user()
    bid = renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(2), "end_date": d(3),
                                                        "protection": "standard", "extras": ["child_seat"]}).json()["id"]
    owner.post(f"/api/bookings/{bid}/approve", headers=H)
    body = renter.get(f"/api/bookings/{bid}/contract").json()["body"]
    assert "Standart" in body and "3 000 000 so'm" in body and "bolalar o'rindig'i" in body and "jarima" in body.lower()
