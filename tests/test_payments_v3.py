"""To'lov tizimi (v3): bekor qilish siyosati, owner kompensatsiyasi, eskirgan urinishlar, to'lovlar tarixi,
pul yechish so'rovlari, Payme chekka holatlari va ChangePassword."""
import base64
import time
from datetime import date, timedelta

import pytest
from starlette.testclient import TestClient

from app.config import settings
from app.db import get_db
from app.main import app
from conftest import H, make_car, make_user


def d(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


def paid_booking(start: int, days: int = 2, price: int = 300_000, provider: str = "test"):
    owner, o = make_user()
    renter, r = make_user()
    car = make_car(owner, price_per_day=price)
    b = renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(start), "end_date": d(start + days - 1)}).json()
    assert owner.post(f"/api/bookings/{b['id']}/approve", headers=H).status_code == 200
    pay = renter.post("/api/payments", headers=H, json={"booking_id": b["id"], "provider": provider}).json()
    if provider == "test":
        assert renter.post(f"/api/payments/{pay['payment_id']}/test/confirm", headers=H).status_code == 200
    return owner, renter, b, pay


# ---------------- Bekor qilish siyosati ----------------
def test_full_refund_three_days_before():
    owner, renter, b, pay = paid_booking(start=5)
    pv = renter.get(f"/api/bookings/{b['id']}/cancel-preview").json()
    assert pv == {**pv, "paid": True, "amount": 600_000, "refund": 600_000, "kept": 0, "pct": 100}
    r = renter.post(f"/api/bookings/{b['id']}/cancel", headers=H).json()
    assert r["refund"]["refund"] == 600_000 and r["refund"]["status"] == "refunded"
    assert owner.get("/api/my/earnings").json()["earned_online"] == 0


def test_half_refund_close_to_start_and_owner_compensation():
    owner, renter, b, pay = paid_booking(start=1)                     # ertaga boshlanadi -> 50%
    pv = renter.get(f"/api/bookings/{b['id']}/cancel-preview").json()
    assert pv["pct"] == 50 and pv["refund"] == 300_000 and pv["kept"] == 300_000
    renter.post(f"/api/bookings/{b['id']}/cancel", headers=H)
    p = renter.get(f"/api/payments/{pay['payment_id']}").json()
    assert p["status"] == "refunded" and p["refund_amount"] == 300_000
    e = owner.get("/api/my/earnings").json()
    assert e["compensation"] == 270_000 and e["earned_online"] == 270_000      # 300 000 − 10% komissiya
    with get_db() as db:
        row = db.execute("SELECT kept_commission + kept_payout, refund_amount FROM payments WHERE id = ?", (pay["payment_id"],)).fetchone()
    assert row[0] + row[1] == 600_000                                          # pul yo'qolmaydi va ortiqcha paydo bo'lmaydi


def test_cancel_preview_only_for_own_booking():
    owner, renter, b, pay = paid_booking(start=5)
    other, _ = make_user()
    assert other.get(f"/api/bookings/{b['id']}/cancel-preview").status_code == 403
    assert owner.get(f"/api/bookings/{b['id']}/cancel-preview").status_code == 403


def test_partial_refund_with_real_provider_waits_for_admin():
    settings.CLICK_SERVICE_ID, settings.CLICK_MERCHANT_ID, settings.CLICK_SECRET_KEY = "100", "200", "secret"
    try:
        admin, _ = make_user("admin")
        owner, renter, b, pay = paid_booking(start=2, provider="click")
        with get_db() as db:   # Click to'lovi muvaffaqiyatli bo'lgandek
            from app.routes.payments import mark_paid
            p = dict(db.execute("SELECT * FROM payments WHERE id = ?", (pay["payment_id"],)).fetchone())
            mark_paid(db, p, "click-1")
        renter.post(f"/api/bookings/{b['id']}/cancel", headers=H)
        p = renter.get(f"/api/payments/{pay['payment_id']}").json()
        assert p["status"] == "refund_pending" and p["refund_amount"] == 300_000
        assert admin.post(f"/api/admin/payments/{pay['payment_id']}/refunded", headers=H).status_code == 200
        assert renter.get(f"/api/payments/{pay['payment_id']}").json()["refund_amount"] == 300_000
    finally:
        settings.CLICK_SERVICE_ID = settings.CLICK_MERCHANT_ID = settings.CLICK_SECRET_KEY = ""


# ---------------- Eskirgan urinishlar va tarix ----------------
def test_stale_checkout_is_closed():
    owner, _ = make_user()
    renter, _ = make_user()
    car = make_car(owner)
    b = renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(5), "end_date": d(5)}).json()
    owner.post(f"/api/bookings/{b['id']}/approve", headers=H)
    pid = renter.post("/api/payments", headers=H, json={"booking_id": b["id"], "provider": "test"}).json()["payment_id"]
    with get_db() as db:
        db.execute("UPDATE payments SET created_at = datetime('now', '-2 hours') WHERE id = ?", (pid,))
    new = renter.post("/api/payments", headers=H, json={"booking_id": b["id"], "provider": "test"}).json()["payment_id"]
    assert new != pid
    assert renter.get(f"/api/payments/{pid}").json()["status"] == "cancelled"


def test_open_attempt_closed_when_booking_cancelled():
    owner, _ = make_user()
    renter, _ = make_user()
    car = make_car(owner)
    b = renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(5), "end_date": d(5)}).json()
    owner.post(f"/api/bookings/{b['id']}/approve", headers=H)
    pid = renter.post("/api/payments", headers=H, json={"booking_id": b["id"], "provider": "test"}).json()["payment_id"]
    renter.post(f"/api/bookings/{b['id']}/cancel", headers=H)
    renter.get("/api/bookings/mine")                                   # fon vazifasi ishlaydi
    assert renter.get(f"/api/payments/{pid}").json()["status"] == "cancelled"
    assert renter.post(f"/api/payments/{pid}/test/confirm", headers=H).status_code == 400


def test_my_payments_history():
    owner, renter, b, pay = paid_booking(start=1)
    renter.post(f"/api/bookings/{b['id']}/cancel", headers=H)
    h = renter.get("/api/my/payments").json()
    assert h["paid_total"] == 600_000 and h["refunded_total"] == 300_000
    assert h["items"][0]["id"] == pay["payment_id"] and h["policy"][0] == {"min_days": 3, "pct": 100}
    other, _ = make_user()
    assert other.get("/api/my/payments").json()["items"] == []


# ---------------- Pul yechish so'rovlari ----------------
def test_payout_request_lifecycle():
    admin, _ = make_user("admin")
    owner, renter, b, pay = paid_booking(start=5)                      # owner balansi 540 000
    bad = owner.post("/api/my/payout-requests", headers=H, json={"amount": 100_000, "method": "card"})
    assert bad.status_code == 422                                      # karta uchun oxirgi 4 raqam kerak
    assert owner.post("/api/my/payout-requests", headers=H,
                      json={"amount": 100_000, "method": "card", "card_last4": "8600123412341234"}).status_code == 422  # to'liq raqam qabul qilinmaydi
    assert owner.post("/api/my/payout-requests", headers=H, json={"amount": 999_999, "method": "cash"}).status_code == 400
    r = owner.post("/api/my/payout-requests", headers=H, json={"amount": 500_000, "method": "card", "card_last4": "1234"})
    assert r.status_code == 201 and r.json()["available"] == 40_000
    assert owner.post("/api/my/payout-requests", headers=H, json={"amount": 10_000, "method": "cash"}).status_code == 409
    assert renter.get("/api/admin/payout-requests").status_code == 403
    items = admin.get("/api/admin/payout-requests").json()["items"]
    req = [i for i in items if i["id"] == r.json()["id"]][0]
    assert req["status"] == "pending" and req["card_last4"] == "1234"
    assert admin.post(f"/api/admin/payout-requests/{req['id']}/reject", headers=H, json={}).status_code == 400  # sabab majburiy
    assert admin.post(f"/api/admin/payout-requests/{req['id']}/approve", headers=H, json={"note": "Uzcard"}).status_code == 200
    assert admin.post(f"/api/admin/payout-requests/{req['id']}/approve", headers=H, json={}).status_code == 400  # ikki marta emas
    e = owner.get("/api/my/earnings").json()
    assert e["paid_out"] == 500_000 and e["balance"] == 40_000 and e["requests"][0]["status"] == "paid"


def test_payout_request_reject_and_cancel():
    admin, _ = make_user("admin")
    owner, renter, b, pay = paid_booking(start=5)
    r1 = owner.post("/api/my/payout-requests", headers=H, json={"amount": 100_000, "method": "bank"}).json()
    assert owner.post(f"/api/my/payout-requests/{r1['id']}/cancel", headers=H).json()["available"] == 540_000
    r2 = owner.post("/api/my/payout-requests", headers=H, json={"amount": 100_000, "method": "bank"}).json()
    assert admin.post(f"/api/admin/payout-requests/{r2['id']}/reject", headers=H, json={"note": "Rekvizit noto'g'ri"}).status_code == 200
    reqs = owner.get("/api/my/earnings").json()["requests"]
    assert reqs[0]["status"] == "rejected" and reqs[0]["admin_note"] == "Rekvizit noto'g'ri"


# ---------------- Payme chekka holatlari ----------------
@pytest.fixture
def payme_on():
    settings.PAYME_MERCHANT_ID, settings.PAYME_KEY = "m123", "paymekey"
    yield
    settings.PAYME_MERCHANT_ID = settings.PAYME_KEY = ""
    with get_db() as db:
        db.execute("DELETE FROM settings WHERE key = 'payme_key'")


def rpc(method, params, key="paymekey"):
    auth = "Basic " + base64.b64encode(f"Paycom:{key}".encode()).decode()
    return TestClient(app).post("/api/payments/payme", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                                headers={"Authorization": auth}).json()


def test_payme_single_active_transaction_and_cancelled_booking(payme_on):
    owner, renter, b, pay = paid_booking(start=5, provider="payme")
    acc, amt, now = {"order_id": str(pay["payment_id"])}, 600_000 * 100, int(time.time() * 1000)
    assert rpc("CreateTransaction", {"id": "a-1", "time": now, "amount": amt, "account": acc})["result"]["state"] == 1
    assert rpc("CheckPerformTransaction", {"amount": amt, "account": acc})["error"]["code"] == -31050
    assert rpc("CreateTransaction", {"id": "a-2", "time": now, "amount": amt, "account": acc})["error"]["code"] == -31050
    renter.post(f"/api/bookings/{b['id']}/cancel", headers=H)          # kutish paytida bekor qildi
    assert rpc("PerformTransaction", {"id": "a-1"})["error"]["code"] == -31008
    assert renter.get(f"/api/payments/{pay['payment_id']}").json()["status"] == "cancelled"


def test_payme_change_password(payme_on):
    assert rpc("ChangePassword", {"password": "yangi-kalit-123"})["result"]["success"] is True
    assert rpc("CheckTransaction", {"id": "x"}, key="paymekey")["error"]["code"] == -32504     # eski kalit endi ishlamaydi
    assert rpc("CheckTransaction", {"id": "x"}, key="yangi-kalit-123")["error"]["code"] == -31003
