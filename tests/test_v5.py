"""v5: kabinetlar bo'yicha bildirishnomalar, xabar konteksti, parolni tiklash javobi, admin foydalanuvchi filtrlari."""
from datetime import date, timedelta

from starlette.testclient import TestClient

from app.main import app
from conftest import H, make_car, make_user


def d(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


def test_notifications_carry_mode_and_actor():
    owner, o = make_user()
    renter, r = make_user()
    car = make_car(owner)
    b = renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(5), "end_date": d(6)}).json()
    n = owner.get("/api/notifications").json()["items"][0]
    assert n["type"] == "booking_new" and n["mode"] == "owner" and n["actor_name"] == r["full_name"]
    owner.post(f"/api/bookings/{b['id']}/approve", headers=H)
    n = renter.get("/api/notifications").json()["items"][0]
    assert n["type"] == "booking_approved" and n["mode"] == "renter" and n["actor_name"] == o["full_name"]


def test_message_context_splits_by_mode():
    owner, o = make_user()
    renter, r = make_user()
    car = make_car(owner)
    renter.post("/api/messages", headers=H, json={"to_user_id": o["id"], "body": "Salom, mashina bo'shmi?", "car_id": car["id"]})
    owner.post("/api/messages", headers=H, json={"to_user_id": r["id"], "body": "Ha, bo'sh.", "car_id": car["id"]})
    s_owner = owner.get("/api/me/summary").json()
    s_renter = renter.get("/api/me/summary").json()
    assert s_owner["msg_by_mode"] == {"owner": 1} and s_owner["notif_by_mode"].get("owner") == 1
    assert s_renter["msg_by_mode"] == {"renter": 1} and s_renter["notif_by_mode"].get("renter") == 1
    n = renter.get("/api/notifications").json()["items"][0]
    assert n["type"] == "message" and n["mode"] == "renter" and "mode=renter" in n["link"] and n["params"]["preview"] == "Ha, bo'sh."
    conv = owner.get("/api/messages").json()["items"][0]
    assert conv["ctx"] == "owner" and renter.get("/api/messages").json()["items"][0]["ctx"] == "renter"
    # "after" bo'yicha faqat yangilari (Telegram uslubidagi oyna uchun)
    last = s_renter["last_notification_id"]
    assert renter.get(f"/api/notifications?after={last}").json()["items"] == []


def test_forgot_reports_channel_is_not_real_without_provider():
    _, u = make_user()
    r = TestClient(app).post("/api/auth/forgot", headers=H, json={"login": u["email"]}).json()
    assert r["real"] is False and r["dev_inbox"] is True and r["ttl_sec"] == r["ttl_min"] * 60 <= 300


def test_admin_user_filters_and_counts():
    admin, _ = make_user("admin")
    blocked, b = make_user()
    admin.patch(f"/api/admin/users/{b['id']}", headers=H, json={"is_active": False})
    res = admin.get("/api/admin/users?kind=blocked").json()
    assert [u["id"] for u in res["items"]] == [b["id"]] or b["id"] in [u["id"] for u in res["items"]]
    assert all(not u["is_active"] for u in res["items"])
    assert res["counts"]["blocked"] >= 1 and res["counts"]["all"] >= res["counts"]["new"] >= 1
    assert all(u["role"] == "admin" for u in admin.get("/api/admin/users?kind=admins").json()["items"])
