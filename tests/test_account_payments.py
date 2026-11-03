"""Yangi funksiyalar: telefon bilan kirish, parolni tiklash, tasdiqlash, sessiyalar, sozlamalar,
to'lovlar (test, Click, Payme), band kunlar, rasm tartibi, shikoyatlar, so'rov hajmi chegarasi."""
import base64
import hashlib
import io
import re
from datetime import date, timedelta

import pytest
from PIL import Image
from starlette.testclient import TestClient

from app.config import settings
from app.db import get_db
from app.main import app
from app.security import account_limiter, code_limiter, forgot_limiter, login_limiter
from conftest import CAR, H, PASSWORD, make_car, make_user

NEW_PW = "Yangi-parol-2026!"


def d(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


@pytest.fixture(autouse=True)
def _reset_limits():
    for lim in (login_limiter, account_limiter, code_limiter, forgot_limiter):
        lim._hits.clear()
    settings.CODE_RESEND_SEC = 0          # testlarda kutmaymiz
    yield
    settings.CODE_RESEND_SEC = 60


def last_code(to: str) -> str:
    with get_db() as db:
        row = db.execute("SELECT body FROM dev_outbox WHERE to_addr = ? ORDER BY id DESC LIMIT 1", (to,)).fetchone()
    assert row, f"{to} uchun xat yo'q"
    return re.search(r"\b(\d{6})\b", row[0]).group(1)


def phone_of(user: dict) -> str:
    return user["phone"]


# ---------------- Kirish va parolni tiklash ----------------
def test_login_with_phone_in_any_format():
    _, u = make_user()
    c = TestClient(app)
    local = u["phone"][-9:]                                    # 77xxxxxxx
    pretty = f"+998 {local[:2]} {local[2:5]}-{local[5:7]}-{local[7:]}"
    for ident in (u["phone"], local, pretty, u["email"].upper()):
        r = c.post("/api/auth/login", headers=H, json={"login": ident, "password": PASSWORD})
        assert r.status_code == 200, (ident, r.text)
    assert c.post("/api/auth/login", headers=H, json={"login": local, "password": "xato-parol-123"}).status_code == 401


def test_forgot_and_reset_by_email():
    owner, u = make_user()
    c = TestClient(app)
    r = c.post("/api/auth/forgot", headers=H, json={"login": u["email"]})
    assert r.status_code == 200 and r.json()["channel"] == "email"
    code = last_code(u["email"])
    assert c.post("/api/auth/reset", headers=H, json={"login": u["email"], "code": "000000" if code != "000000" else "111111",
                                                       "new_password": NEW_PW}).status_code == 400
    r = c.post("/api/auth/reset", headers=H, json={"login": u["email"], "code": code, "new_password": NEW_PW})
    assert r.status_code == 200 and r.json()["user"]["email_verified"] is True
    assert owner.get("/api/auth/me").json()["user"] is None                         # eski sessiya yopildi
    assert c.post("/api/auth/reset", headers=H, json={"login": u["email"], "code": code, "new_password": NEW_PW}).status_code == 400  # bir martalik
    assert TestClient(app).post("/api/auth/login", headers=H, json={"login": u["email"], "password": NEW_PW}).status_code == 200


def test_forgot_and_reset_by_phone_sms():
    _, u = make_user()
    c = TestClient(app)
    r = c.post("/api/auth/forgot", headers=H, json={"login": u["phone"][-9:]})
    assert r.json()["channel"] == "sms"
    code = last_code(u["phone"])
    r = c.post("/api/auth/reset", headers=H, json={"login": u["phone"], "code": code, "new_password": NEW_PW})
    assert r.status_code == 200 and r.json()["user"]["phone_verified"] is True


def test_forgot_does_not_reveal_accounts():
    c = TestClient(app)
    a = c.post("/api/auth/forgot", headers=H, json={"login": "yoq-odam@t.uz"}).json()
    _, u = make_user()
    b = c.post("/api/auth/forgot", headers=H, json={"login": u["email"]}).json()
    assert a["message"] == b["message"]


def test_code_attempts_limited():
    _, u = make_user()
    c = TestClient(app)
    c.post("/api/auth/forgot", headers=H, json={"login": u["email"]})
    code = last_code(u["email"])
    wrong = "123456" if code != "123456" else "654321"
    for _ in range(settings.CODE_MAX_ATTEMPTS):
        c.post("/api/auth/reset", headers=H, json={"login": u["email"], "code": wrong, "new_password": NEW_PW})
    # 5 ta xato urinishdan keyin to'g'ri kod ham ishlamaydi
    assert c.post("/api/auth/reset", headers=H, json={"login": u["email"], "code": code, "new_password": NEW_PW}).status_code == 400


def test_code_expiry_and_resend_cooldown():
    _, u = make_user()
    c = TestClient(app)
    c.post("/api/auth/forgot", headers=H, json={"login": u["email"]})
    code = last_code(u["email"])
    with get_db() as db:
        db.execute("UPDATE verification_codes SET expires_at = datetime('now', '-1 minute') WHERE target = ?", (u["email"],))
    assert c.post("/api/auth/reset", headers=H, json={"login": u["email"], "code": code, "new_password": NEW_PW}).status_code == 400
    settings.CODE_RESEND_SEC = 60
    me, _ = make_user()
    me.post("/api/me/verify/start", headers=H, json={"channel": "email"})
    assert me.post("/api/me/verify/start", headers=H, json={"channel": "email"}).status_code == 429


def test_spoofed_forwarded_for_does_not_bypass_limit():
    c = TestClient(app)
    codes = [c.post("/api/auth/login", json={"login": "x@t.uz", "password": "y"},
                    headers={**H, "X-Forwarded-For": f"10.0.0.{i}"}).status_code for i in range(10)]
    assert 429 in codes


# ---------------- Tasdiqlash, sozlamalar, sessiyalar ----------------
def test_verify_email_and_phone():
    c, u = make_user(verified=False)
    assert c.get("/api/auth/me").json()["user"]["email_verified"] is False
    assert c.post("/api/me/verify/start", headers=H, json={"channel": "email"}).json()["sent_to"].startswith(u["email"][0])
    r = c.post("/api/me/verify/confirm", headers=H, json={"channel": "email", "code": last_code(u["email"])})
    assert r.json()["user"]["email_verified"] is True
    c.post("/api/me/verify/start", headers=H, json={"channel": "sms"})
    r = c.post("/api/me/verify/confirm", headers=H, json={"channel": "sms", "code": last_code(u["phone"])})
    assert r.json()["user"]["phone_verified"] is True


def test_sessions_list_revoke_and_password_change():
    a, u = make_user()
    b = TestClient(app)
    b.post("/api/auth/login", headers=H, json={"login": u["email"], "password": PASSWORD})
    items = a.get("/api/me/sessions").json()["items"]
    assert len(items) == 2 and sum(s["current"] for s in items) == 1
    # Parol o'zgarsa boshqa qurilma chiqariladi, joriy qoladi
    assert a.post("/api/auth/change-password", headers=H, json={"old_password": PASSWORD, "new_password": NEW_PW}).status_code == 200
    assert a.get("/api/auth/me").json()["user"] is not None
    assert b.get("/api/auth/me").json()["user"] is None
    # Logout sessiyani bazada yopadi: o'g'irlangan cookie qayta ishlamaydi
    token = a.cookies.get("access_token")
    a.post("/api/auth/logout", headers=H)
    thief = TestClient(app); thief.cookies.set("access_token", token)
    assert thief.get("/api/auth/me").json()["user"] is None


def test_logout_all_devices():
    a, u = make_user()
    b = TestClient(app)
    b.post("/api/auth/login", headers=H, json={"login": u["email"], "password": PASSWORD})
    assert a.post("/api/me/logout-all", headers=H).status_code == 200
    assert b.get("/api/auth/me").json()["user"] is None and a.get("/api/auth/me").json()["user"] is not None


def test_prefs_and_phone_privacy():
    owner, o = make_user()
    car = make_car(owner)
    viewer, _ = make_user()
    assert viewer.get(f"/api/cars/{car['id']}").json()["owner"]["phone"] == o["phone"]
    r = owner.put("/api/me/prefs", headers=H, json={"show_phone": False, "marketing_ok": True, "email_booking": False,
                                                     "email_messages": True, "sms_booking": False})
    assert r.json()["user"]["notify_prefs"]["email_messages"] is True and r.json()["user"]["show_phone"] is False
    assert viewer.get(f"/api/cars/{car['id']}").json()["owner"]["phone"] is None


def test_email_change_requires_password_and_code():
    c, u = make_user()
    assert c.post("/api/me/email/start", headers=H, json={"new_email": "yangi@t.uz", "password": "xato-parol-123"}).status_code == 400
    assert c.post("/api/me/email/start", headers=H, json={"new_email": "yangi@t.uz", "password": PASSWORD}).status_code == 200
    r = c.post("/api/me/email/confirm", headers=H, json={"code": last_code("yangi@t.uz")})
    assert r.json()["user"]["email"] == "yangi@t.uz"
    with get_db() as db:   # eski manzilga xavfsizlik xati ketdi
        assert db.execute("SELECT 1 FROM dev_outbox WHERE to_addr = ? AND subject LIKE '%xavfsizlik%'", (u["email"],)).fetchone()


def test_delete_account():
    c, u = make_user()
    owner, _ = make_user()
    car = make_car(owner)
    b = c.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(3), "end_date": d(4)}).json()
    assert c.post("/api/me/delete", headers=H, json={"password": PASSWORD}).status_code == 409      # faol bron bor
    c.post(f"/api/bookings/{b['id']}/cancel", headers=H)
    assert c.post("/api/me/delete", headers=H, json={"password": "xato-parol-123"}).status_code == 400
    assert c.post("/api/me/delete", headers=H, json={"password": PASSWORD}).status_code == 200
    assert TestClient(app).post("/api/auth/login", headers=H, json={"login": u["email"], "password": PASSWORD}).status_code == 401


def test_avatar_upload():
    c, _ = make_user()
    buf = io.BytesIO(); Image.new("RGB", (800, 500), (10, 120, 200)).save(buf, "PNG")
    r = c.post("/api/me/avatar", headers=H, files={"avatar": ("me.png", buf.getvalue(), "image/png")})
    assert r.status_code == 200
    im = Image.open(io.BytesIO(c.get(r.json()["user"]["avatar"]).content))
    assert im.size[0] == im.size[1] <= 320


# ---------------- To'lovlar ----------------
def approved_booking(price=300_000):
    owner, o = make_user()
    renter, r = make_user()
    car = make_car(owner, price_per_day=price)
    b = renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(5), "end_date": d(6)}).json()
    owner.post(f"/api/bookings/{b['id']}/approve", headers=H)
    return owner, renter, b


def test_test_payment_flow_and_refund():
    owner, renter, b = approved_booking()
    other, _ = make_user()
    assert other.post("/api/payments", headers=H, json={"booking_id": b["id"], "provider": "test"}).status_code == 403
    r = renter.post("/api/payments", headers=H, json={"booking_id": b["id"], "provider": "test"}).json()
    assert r["amount"] == 600_000 and r["redirect_url"].startswith("/pay.html")
    again = renter.post("/api/payments", headers=H, json={"booking_id": b["id"], "provider": "test"}).json()
    assert again["payment_id"] == r["payment_id"]                                   # takroriy urinish qayta ishlatiladi
    assert other.get(f"/api/payments/{r['payment_id']}").status_code == 404           # begona ko'ra olmaydi
    assert renter.post(f"/api/payments/{r['payment_id']}/test/confirm", headers=H).status_code == 200
    inc = [x for x in owner.get("/api/bookings/incoming").json()["items"] if x["id"] == b["id"]][0]
    assert inc["payment_status"] == "paid" and inc["payment_id"] == r["payment_id"]
    assert renter.post("/api/payments", headers=H, json={"booking_id": b["id"], "provider": "test"}).status_code == 409
    assert owner.get("/api/my/earnings").json()["earned_online"] == 540_000          # 600 000 − 10%
    renter.post(f"/api/bookings/{b['id']}/cancel", headers=H)
    p = renter.get(f"/api/payments/{r['payment_id']}").json()
    assert p["status"] == "refunded"


def test_cannot_pay_pending_booking():
    owner, _ = make_user()
    renter, _ = make_user()
    car = make_car(owner)
    b = renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(5), "end_date": d(6)}).json()
    assert renter.post("/api/payments", headers=H, json={"booking_id": b["id"], "provider": "test"}).status_code == 400
    assert renter.post("/api/payments", headers=H, json={"booking_id": b["id"], "provider": "click"}).status_code == 400  # ulanmagan


@pytest.fixture
def click_on():
    settings.CLICK_SERVICE_ID, settings.CLICK_MERCHANT_ID, settings.CLICK_SECRET_KEY = "100", "200", "secret"
    yield
    settings.CLICK_SERVICE_ID = settings.CLICK_MERCHANT_ID = settings.CLICK_SECRET_KEY = ""


def click_form(pid, amount, action, prepare_id="", error="0", key="secret"):
    f = {"click_trans_id": f"77{pid}", "service_id": "100", "click_paydoc_id": "1", "merchant_trans_id": str(pid),
         "amount": str(amount), "action": str(action), "error": error, "error_note": "", "sign_time": "2026-10-30 10:00:00"}
    if prepare_id:
        f["merchant_prepare_id"] = prepare_id
    base = f["click_trans_id"] + f["service_id"] + key + f["merchant_trans_id"] + prepare_id + f["amount"] + f["action"] + f["sign_time"]
    f["sign_string"] = hashlib.md5(base.encode()).hexdigest()
    return f


def test_click_prepare_complete(click_on):
    owner, renter, b = approved_booking()
    r = renter.post("/api/payments", headers=H, json={"booking_id": b["id"], "provider": "click"}).json()
    assert "my.click.uz" in r["redirect_url"]
    c = TestClient(app)   # Click serveri: CSRF sarlavhasisiz
    assert c.post("/api/payments/click", data=click_form(r["payment_id"], 600000, 0, key="xato")).json()["error"] == -1
    assert c.post("/api/payments/click", data=click_form(r["payment_id"], 1, 0)).json()["error"] == -2
    prep = c.post("/api/payments/click", data=click_form(r["payment_id"], 600000, 0)).json()
    assert prep["error"] == 0 and prep["merchant_prepare_id"] == r["payment_id"]
    done = c.post("/api/payments/click", data=click_form(r["payment_id"], 600000, 1, str(r["payment_id"]))).json()
    assert done["error"] == 0
    assert renter.get(f"/api/payments/{r['payment_id']}").json()["status"] == "paid"
    assert c.post("/api/payments/click", data=click_form(r["payment_id"], 600000, 1, str(r["payment_id"]))).json()["error"] == -4


@pytest.fixture
def payme_on():
    settings.PAYME_MERCHANT_ID, settings.PAYME_KEY = "m123", "paymekey"
    yield
    settings.PAYME_MERCHANT_ID = settings.PAYME_KEY = ""


def rpc(method, params, key="paymekey"):
    auth = "Basic " + base64.b64encode(f"Paycom:{key}".encode()).decode()
    return TestClient(app).post("/api/payments/payme", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                                headers={"Authorization": auth}).json()


def test_payme_full_cycle(payme_on):
    owner, renter, b = approved_booking()
    r = renter.post("/api/payments", headers=H, json={"booking_id": b["id"], "provider": "payme"}).json()
    acc, amt = {"order_id": str(r["payment_id"])}, 600_000 * 100
    assert rpc("CheckPerformTransaction", {"amount": amt, "account": acc}, key="xato")["error"]["code"] == -32504
    assert rpc("CheckPerformTransaction", {"amount": amt + 1, "account": acc})["error"]["code"] == -31001
    assert rpc("CheckPerformTransaction", {"amount": amt, "account": {"order_id": "999999"}})["error"]["code"] == -31050
    assert rpc("CheckPerformTransaction", {"amount": amt, "account": acc})["result"]["allow"] is True
    import time
    now = int(time.time() * 1000)
    cr = rpc("CreateTransaction", {"id": "pm-1", "time": now, "amount": amt, "account": acc})["result"]
    assert cr["state"] == 1
    assert rpc("CreateTransaction", {"id": "pm-1", "time": now, "amount": amt, "account": acc})["result"]["state"] == 1  # idempotent
    pf = rpc("PerformTransaction", {"id": "pm-1"})["result"]
    assert pf["state"] == 2
    assert rpc("CheckTransaction", {"id": "pm-1"})["result"]["state"] == 2
    assert renter.get(f"/api/payments/{r['payment_id']}").json()["status"] == "paid"
    cancel = rpc("CancelTransaction", {"id": "pm-1", "reason": 5})["result"]
    assert cancel["state"] == -2
    assert rpc("CheckTransaction", {"id": "nope"})["error"]["code"] == -31003
    assert rpc("Nope", {})["error"]["code"] == -32601


def test_admin_payout_and_refund_pending(click_on):
    admin, _ = make_user("admin")
    owner, renter, b = approved_booking()
    r = renter.post("/api/payments", headers=H, json={"booking_id": b["id"], "provider": "click"}).json()
    c = TestClient(app)
    c.post("/api/payments/click", data=click_form(r["payment_id"], 600000, 0))
    c.post("/api/payments/click", data=click_form(r["payment_id"], 600000, 1, str(r["payment_id"])))
    owner_id = owner.get("/api/auth/me").json()["user"]["id"]
    assert admin.post("/api/admin/payouts", headers=H, json={"owner_id": owner_id, "amount": 10_000_000}).status_code == 400
    bal = admin.post("/api/admin/payouts", headers=H, json={"owner_id": owner_id, "amount": 540_000}).json()
    assert bal["balance"] == 0
    renter.post(f"/api/bookings/{b['id']}/cancel", headers=H)          # real provayder: admin tasdiqlaydi
    assert renter.get(f"/api/payments/{r['payment_id']}").json()["status"] == "refund_pending"
    assert admin.post(f"/api/admin/payments/{r['payment_id']}/refunded", headers=H).status_code == 200


# ---------------- Band kunlar, rasmlar, shikoyatlar ----------------
def test_owner_blocks_dates():
    owner, _ = make_user()
    renter, _ = make_user()
    stranger, _ = make_user()
    car = make_car(owner)
    assert stranger.post(f"/api/cars/{car['id']}/blocks", headers=H, json={"start_date": d(10), "end_date": d(12)}).status_code == 403
    blk = owner.post(f"/api/cars/{car['id']}/blocks", headers=H, json={"start_date": d(10), "end_date": d(12), "note": "Ta'mir"}).json()
    assert renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(11), "end_date": d(13)}).status_code == 409
    cal = renter.get(f"/api/cars/{car['id']}/calendar").json()["ranges"]
    assert any(r["status"] == "blocked" for r in cal)
    assert car["id"] not in [c["id"] for c in renter.get("/api/cars", params={"start": d(11), "end": d(11), "limit": 48}).json()["items"]]
    owner.delete(f"/api/cars/{car['id']}/blocks/{blk['id']}", headers=H)
    assert renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(11), "end_date": d(13)}).status_code == 201


def test_image_order_and_labels():
    owner, _ = make_user()
    car = make_car(owner)
    imgs = []
    for color in ((255, 0, 0), (0, 255, 0)):
        buf = io.BytesIO(); Image.new("RGB", (60, 40), color).save(buf, "PNG"); imgs.append(buf.getvalue())
    r = owner.post(f"/api/cars/{car['id']}/images", headers=H, data={"labels": ["front", "interior"]},
                   files=[("images", ("a.png", imgs[0], "image/png")), ("images", ("b.png", imgs[1], "image/png"))]).json()["images"]
    assert [i["label"] for i in r] == ["front", "interior"]
    rev = owner.put(f"/api/cars/{car['id']}/images/order", headers=H, json={"ids": [r[1]["id"], r[0]["id"]]}).json()["images"]
    assert rev[0]["id"] == r[1]["id"]
    assert owner.patch(f"/api/cars/{car['id']}/images/{r[0]['id']}", headers=H, json={"label": "back"}).json()["label"] == "back"
    assert owner.put(f"/api/cars/{car['id']}/images/order", headers=H, json={"ids": [r[0]["id"]]}).status_code == 400


def test_reports_flow():
    admin, _ = make_user("admin")
    owner, _ = make_user()
    reporter, _ = make_user()
    car = make_car(owner, brand="Shikoyat")
    assert reporter.post("/api/reports", headers=H, json={"target_type": "car", "target_id": car["id"], "reason": "fake"}).status_code == 201
    assert reporter.post("/api/reports", headers=H, json={"target_type": "car", "target_id": car["id"], "reason": "fake"}).status_code == 409
    assert reporter.post("/api/reports", headers=H, json={"target_type": "car", "target_id": 999999, "reason": "fake"}).status_code == 404
    items = admin.get("/api/admin/reports").json()["items"]
    rep = [x for x in items if x["target_id"] == car["id"]][0]
    assert "Shikoyat" in rep["target_label"]
    admin.patch(f"/api/admin/reports/{rep['id']}", headers=H, json={"status": "resolved", "action": "hide_car"})
    assert reporter.get("/api/cars", params={"brand": "Shikoyat"}).json()["total"] == 0


def test_body_size_limit():
    c, _ = make_user()
    big = {"full_name": "x" * 70_000, "phone": "+998901112233"}
    assert c.put("/api/auth/me", headers=H, json=big).status_code == 413


def test_booking_notification_mirrored_to_email():
    owner, o = make_user()
    renter, _ = make_user()
    car = make_car(owner)
    renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(7), "end_date": d(8)})
    with get_db() as db:
        row = db.execute("SELECT subject, body FROM dev_outbox WHERE to_addr = ? ORDER BY id DESC LIMIT 1", (o["email"],)).fetchone()
    assert row and "bron" in row[0].lower()


def test_merged_info_page_and_static_pages(client):
    r = client.get("/about.html", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/info.html"
    for page in ("/info.html", "/settings.html", "/pay.html", "/receipt.html", "/dev-inbox.html", "/offline.html", "/sw.js",
                 "/manifest.webmanifest", "/img/icon-192.png"):
        assert client.get(page).status_code == 200, page
    assert "manifest" in client.get("/manifest.webmanifest").headers["content-type"]


def test_meta_reports_channel_flags(client):
    m = client.get("/api/meta").json()
    assert m["payments"]["click"] is False and m["payments"]["payme"] is False   # kalitsiz — ulanmagan
    assert m["email_real"] is False and m["sms_real"] is False
    assert m["max_images"] >= 6


def test_dev_inbox_only_from_local_network():
    remote = TestClient(app, client=("8.8.8.8", 5000))
    assert remote.get("/api/dev/outbox").status_code == 404
    local = TestClient(app, client=("192.168.1.20", 5000))
    assert local.get("/api/dev/outbox").status_code == 200


def test_admin_summary_counts_open_reports():
    owner, _ = make_user()
    car = make_car(owner)
    reporter, _ = make_user()
    assert reporter.post("/api/reports", json={"target_type": "car", "target_id": car["id"], "reason": "fake"}, headers=H).status_code in (200, 201)
    admin, _ = make_user("admin")
    s = admin.get("/api/me/summary").json()
    assert s["open_reports"] >= 1
    assert reporter.get("/api/me/summary").json()["open_reports"] == 0
