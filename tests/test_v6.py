"""v6: batafsil ko'rish (drill-down) va admin — foydalanuvchi sahifasi, amallar, shikoyatdan odamga o'tish."""
from datetime import date, timedelta

from conftest import H, make_car, make_user


def d(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


def _booked():
    owner, o = make_user()
    renter, r = make_user()
    car = make_car(owner)
    b = renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(5), "end_date": d(7)}).json()
    owner.post(f"/api/bookings/{b['id']}/approve", headers=H)
    return owner, o, renter, r, car, b


def test_drill_bookings_scoped_and_summarised():
    owner, o, renter, r, car, b = _booked()
    stranger, _ = make_user()
    mine = owner.get(f"/api/drill?scope=owner&entity=bookings&status=done&car_id={car['id']}").json()
    assert [x["id"] for x in mine["items"]] == [b["id"]]
    it = mine["items"][0]
    assert it["renter_name"] == r["full_name"] and it["commission"] + it["owner_payout"] == it["total_price"]
    assert mine["summary"]["count"] == 1 and mine["summary"]["total"] == it["total_price"] and "renter_phone" not in it
    # Ijarachi komissiya/owner ulushini ko'rmaydi; begona odam esa bu bronni umuman ko'rmaydi
    rv = renter.get("/api/drill?scope=renter&entity=bookings").json()
    assert rv["items"][0]["id"] == b["id"] and "commission" not in rv["items"][0] and "payout" not in rv["summary"]
    assert stranger.get(f"/api/drill?scope=owner&entity=bookings&car_id={car['id']}").json()["items"] == []
    # Filtrlar: shahar, oy, holat
    month = d(5)[:7]
    assert owner.get(f"/api/drill?scope=owner&entity=bookings&month={month}&city={car['city']}").json()["summary"]["count"] == 1
    assert owner.get("/api/drill?scope=owner&entity=bookings&status=cancelled").json()["items"] == []


def test_drill_permissions_and_validation():
    user, _ = make_user()
    assert user.get("/api/drill?scope=admin&entity=bookings").status_code == 403
    assert user.get("/api/drill?scope=owner&entity=users").status_code == 403
    assert user.get("/api/drill?scope=renter&entity=cars").status_code == 403
    assert user.get("/api/drill?scope=owner&entity=bookings&status=hacked").status_code == 400
    assert user.get("/api/drill?scope=owner&entity=nope").status_code == 400
    assert user.get("/api/drill?scope=owner&entity=bookings&month=2026-1x").status_code == 400


def test_drill_cars_and_admin_entities():
    owner, o, renter, r, car, b = _booked()
    admin, _ = make_user("admin")
    cars = owner.get(f"/api/drill?scope=owner&entity=cars&p_from={d(0)}&p_to={d(10)}").json()
    c = cars["items"][0]
    assert c["id"] == car["id"] and c["busy_days"] == 3 and c["trips"] == 1 and c["occupancy"] == round(100 * 3 / 11, 1)
    users = admin.get(f"/api/drill?scope=admin&entity=users&month={date.today().isoformat()[:7]}").json()
    assert {o["id"], r["id"]} <= {u["id"] for u in users["items"]}
    by_user = admin.get(f"/api/drill?scope=admin&entity=bookings&user_id={o['id']}").json()
    assert [x["id"] for x in by_user["items"]] == [b["id"]] and by_user["items"][0]["renter_phone"]
    assert admin.get("/api/drill?scope=admin&entity=payouts").status_code == 200
    assert admin.get("/api/drill?scope=admin&entity=reviews").status_code == 200


def test_admin_user_page_and_actions():
    owner, o, renter, r, car, b = _booked()
    admin, _ = make_user("admin")
    page = admin.get(f"/api/admin/users/{o['id']}").json()
    assert page["user"]["email"] == o["email"] and page["owner"]["cars_total"] == 1 and page["owner"]["statuses"]["approved"] == 1
    assert page["bookings"][0]["id"] == b["id"] and "password_hash" not in page["user"]
    # Ogohlantirish: foydalanuvchiga bildirishnoma, eslatmalarda saqlanadi
    assert admin.post(f"/api/admin/users/{o['id']}/action", headers=H, json={"action": "warn"}).status_code == 422
    assert admin.post(f"/api/admin/users/{o['id']}/action", headers=H, json={"action": "warn", "reason": "Narxni noto'g'ri yozgansiz"}).status_code == 200
    n = owner.get("/api/notifications").json()["items"][0]
    assert n["type"] == "admin_warning" and n["params"]["text"] == "Narxni noto'g'ri yozgansiz"
    # E'lonlarni yashirish va qaytarish
    admin.post(f"/api/admin/users/{o['id']}/action", headers=H, json={"action": "hide_cars", "reason": "Tekshiruv"})
    page = admin.get(f"/api/admin/users/{o['id']}").json()
    assert page["owner"]["cars_active"] == 0 and page["counts"]["warnings"] == 1 and len(page["notes"]) == 2
    admin.post(f"/api/admin/users/{o['id']}/action", headers=H, json={"action": "restore_cars"})
    assert admin.get(f"/api/admin/users/{o['id']}").json()["owner"]["cars_active"] == 1
    # Tasdiqlash va bloklash: bloklangan foydalanuvchi sessiyasi yopiladi
    admin.post(f"/api/admin/users/{r['id']}/action", headers=H, json={"action": "verify_phone"})
    assert admin.get(f"/api/admin/users/{r['id']}").json()["user"]["phone_verified"] == 1
    admin.post(f"/api/admin/users/{r['id']}/action", headers=H, json={"action": "block", "reason": "Firibgarlik"})
    assert renter.get("/api/auth/me").json()["user"] is None and renter.get("/api/bookings/mine").status_code == 401
    # Adminni bloklab bo'lmaydi
    _, a2 = make_user("admin")
    assert admin.post(f"/api/admin/users/{a2['id']}/action", headers=H, json={"action": "block", "reason": "test qilish"}).status_code == 400


def test_admin_cancel_booking_notifies_both():
    owner, o, renter, r, car, b = _booked()
    admin, _ = make_user("admin")
    assert admin.post(f"/api/admin/bookings/{b['id']}/cancel", headers=H, json={"reason": "x"}).status_code == 422
    res = admin.post(f"/api/admin/bookings/{b['id']}/cancel", headers=H, json={"reason": "Mashina hujjatlari soxta"})
    assert res.status_code == 200
    for c in (owner, renter):
        n = c.get("/api/notifications").json()["items"][0]
        assert n["type"] == "booking_cancelled_admin" and n["params"]["text"] == "Mashina hujjatlari soxta"
    assert admin.post(f"/api/admin/bookings/{b['id']}/cancel", headers=H, json={"reason": "yana bir marta"}).status_code == 400
    assert renter.post(f"/api/admin/bookings/{b['id']}/cancel", headers=H, json={"reason": "men adminman"}).status_code == 403


def test_report_points_to_person_and_warn_user():
    owner, o, renter, r, car, b = _booked()
    admin, _ = make_user("admin")
    renter.post("/api/reports", headers=H, json={"target_type": "car", "target_id": car["id"], "reason": "fake", "comment": "Rasmlar boshqa mashinaniki"})
    rep = next(x for x in admin.get("/api/admin/reports").json()["items"] if x["target_id"] == car["id"])
    assert rep["target_user_id"] == o["id"] and rep["target_user_name"] == o["full_name"]
    page = admin.get(f"/api/admin/users/{o['id']}").json()
    assert page["counts"]["complaints_new"] == 1 and any(f["code"] == "complaints" for f in page["flags"])
    admin.patch(f"/api/admin/reports/{rep['id']}", headers=H, json={"status": "resolved", "action": "warn_user", "note": "Haqiqiy rasm qo'ying"})
    n = owner.get("/api/notifications").json()["items"][0]
    assert n["type"] == "admin_warning" and n["params"]["reason"] == "fake"
    assert admin.get(f"/api/admin/users/{o['id']}").json()["counts"]["warnings"] == 1
