"""Nizolar (foydalanuvchilar o'rtasidagi muammolar -> admin qarori) va SMS/email kanallari paneli."""
from datetime import date, timedelta

from starlette.testclient import TestClient

from app import channels
from app.db import get_db
from app.main import app
from conftest import H, make_car, make_user


def d(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


def booking(status="completed"):
    owner, o = make_user()
    renter, r = make_user()
    car = make_car(owner)
    b = renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(3), "end_date": d(4)}).json()
    owner.post(f"/api/bookings/{b['id']}/approve", headers=H)
    if status == "completed":
        with get_db() as db:
            db.execute("UPDATE bookings SET start_date = ?, end_date = ?, status = 'completed' WHERE id = ?", (d(-6), d(-5), b["id"]))
    return owner, o, renter, r, b


def notif_types(client):
    return [n["type"] for n in client.get("/api/notifications").json()["items"]]


def test_dispute_full_cycle():
    admin, _ = make_user("admin")
    owner, o, renter, r, b = booking()
    body = {"booking_id": b["id"], "type": "damage", "description": "Orqa bamper tirnalgan holda qaytarildi, rasmlari chatda.", "amount": 400_000}
    other, _ = make_user()
    assert other.post("/api/disputes", headers=H, json=body).status_code == 404                     # begona bron
    assert owner.post("/api/disputes", headers=H, json={**body, "description": "qisqa"}).status_code == 422
    dsp = owner.post("/api/disputes", headers=H, json=body).json()
    assert dsp["status"] == "open" and dsp["against_id"] == r["id"]
    assert renter.post("/api/disputes", headers=H, json={**body, "type": "deposit"}).status_code == 409   # bitta ochiq nizo
    assert "dispute_opened" in notif_types(renter) and "dispute_new_admin" in notif_types(admin)
    assert owner.post(f"/api/disputes/{dsp['id']}/reply", headers=H, json={"text": "o'zim yozolmayman"}).status_code == 403
    assert renter.post(f"/api/disputes/{dsp['id']}/reply", headers=H, json={"text": "Tirnalish oldindan bor edi, rasmim bor."}).status_code == 200
    assert renter.get("/api/disputes/mine").json()["items"][0]["response"].startswith("Tirnalish")
    assert renter.get("/api/admin/disputes").status_code == 403
    assert admin.get("/api/admin/disputes").json()["items"][0]["id"] == dsp["id"]
    assert admin.post(f"/api/admin/disputes/{dsp['id']}/take", headers=H).json()["status"] == "in_review"
    bad = admin.post(f"/api/admin/disputes/{dsp['id']}/resolve", headers=H, json={"outcome": "split", "note": "Teng bo'lish", "block_user_id": other.get("/api/auth/me").json()["user"]["id"]})
    assert bad.status_code == 400                                                                     # begonani bloklab bo'lmaydi
    res = admin.post(f"/api/admin/disputes/{dsp['id']}/resolve", headers=H,
                     json={"outcome": "split", "note": "Ta'mir xarajati teng bo'linadi: ijarachi ownerga 200 000 to'laydi.", "compensation": 200_000}).json()
    assert res["status"] == "resolved" and res["compensation"] == 200_000
    assert "dispute_resolved" in notif_types(owner) and "dispute_resolved" in notif_types(renter)
    assert admin.post(f"/api/admin/disputes/{dsp['id']}/resolve", headers=H, json={"outcome": "rejected", "note": "yana bir bor"}).status_code == 400


def test_dispute_rules_withdraw_and_block():
    admin, _ = make_user("admin")
    owner, o, renter, r, b = booking(status="approved")
    pend_owner, _ = make_user()
    pend_renter, _ = make_user()
    car = make_car(pend_owner)
    pend = pend_renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(9), "end_date": d(9)}).json()
    assert pend_renter.post("/api/disputes", headers=H, json={"booking_id": pend["id"], "type": "other", "description": "Kutilayotgan bron uchun nizo bo'lmaydi."}).status_code == 400
    dsp = renter.post("/api/disputes", headers=H, json={"booking_id": b["id"], "type": "not_as_described", "description": "E'londa konditsioner bor deyilgan, aslida ishlamaydi."}).json()
    assert owner.post(f"/api/disputes/{dsp['id']}/withdraw", headers=H).status_code == 403
    assert renter.post(f"/api/disputes/{dsp['id']}/withdraw", headers=H).json()["status"] == "cancelled"
    dsp2 = renter.post("/api/disputes", headers=H, json={"booking_id": b["id"], "type": "no_show", "description": "Owner kelishilgan vaqtda kelmadi, telefonni ham olmadi."}).json()
    res = admin.post(f"/api/admin/disputes/{dsp2['id']}/resolve", headers=H,
                     json={"outcome": "favor_opener", "note": "Owner aybdor, akkaunt bloklandi.", "block_user_id": o["id"]}).json()
    assert res["outcome"] == "favor_opener"
    assert owner.get("/api/auth/me").json()["user"] is None                                           # sessiyasi yopildi
    with get_db() as db:   # eski muddat: 30 kundan keyin ochib bo'lmaydi
        db.execute("UPDATE bookings SET end_date = ?, start_date = ? WHERE id = ?", (d(-40), d(-41), b["id"]))
    assert renter.post("/api/disputes", headers=H, json={"booking_id": b["id"], "type": "other", "description": "Juda kech yozilgan nizo matni."}).status_code == 400


def test_channels_panel_and_test_message_dev_inbox():
    admin, _ = make_user("admin")
    user, _ = make_user()
    assert user.get("/api/admin/channels").status_code == 403
    info = admin.get("/api/admin/channels").json()
    assert info["sms"]["enabled"] is False and {t["key"] for t in info["templates"]} >= {"reset", "verify_phone"}
    r = admin.post("/api/admin/channels/test", headers=H, json={"channel": "sms", "to": "90 123 45 67"}).json()
    assert r["status"] == "dev_inbox" and r["to"].startswith("+998")
    assert admin.post("/api/admin/channels/test", headers=H, json={"channel": "sms", "to": "12345"}).status_code == 400
    log = admin.get("/api/admin/channels").json()["log"]
    assert log[0]["template"] == "test" and log[0]["status"] == "dev" and "123" not in log[0]["to_masked"][5:9]


def test_sms_templates_are_short_and_safe():
    for key, langs in channels.SMS_TEMPLATES.items():
        for lang, text in langs.items():
            body = text.format(code="123456", ttl=10, title="Bron tasdiqlandi")
            assert len(body) <= 160 or lang == "ru", (key, lang, len(body))     # bitta SMS (lotin)
            assert "CarRent" in body


def test_eskiz_send_retries_on_expired_token(monkeypatch):
    calls = []

    def fake_post(path, data, token=None):
        calls.append((path, token))
        if path == "auth/login":
            return {"data": {"token": f"tok{len(calls)}"}}
        if token == "tok1":
            raise channels.EskizError(401, "Expired")
        return {"id": "abc", "status": "waiting"}
    monkeypatch.setattr(channels, "_eskiz_post", fake_post)
    channels._eskiz_token.update(value=None, at=0)
    res = channels._eskiz_send("+998901234567", "CarRent: test")
    assert res == {"status": "sent", "provider_id": "abc"}
    assert [c[0] for c in calls] == ["auth/login", "message/sms/send", "auth/login", "message/sms/send"]
    channels._eskiz_token.update(value=None, at=0)


def test_eskiz_callback_requires_signature():
    c = TestClient(app)
    with get_db() as db:
        lid = db.execute("INSERT INTO message_log (channel, to_masked, template, status) VALUES ('sms', '+998 ** *** 45 67', 'reset', 'sent')").lastrowid
    assert c.post(f"/api/channels/eskiz/callback?log={lid}&sig=bad", data={"status": "DELIVRD"}).status_code == 403
    assert c.post(f"/api/channels/eskiz/callback?log={lid}&sig={channels.callback_sig(lid)}", data={"status": "DELIVRD"}).status_code == 200
    with get_db() as db:
        assert db.execute("SELECT status FROM message_log WHERE id = ?", (lid,)).fetchone()[0] == "delivered"
