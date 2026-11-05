"""v8: bron oldidan profil tayyorligi, admin foydalanuvchini to'liq boshqaradi (profil, parol, hujjat, karta, e'lon),
hisobotlarning har bir qismi batafsil ochiladi (har uch rol uchun), maslahatchida arzon variant oldinda."""
from datetime import date, timedelta

from starlette.testclient import TestClient

from app.db import get_db
from app.main import app
from conftest import H, PASSWORD, make_car, make_user
from test_v7 import jpg


def d(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


# ---------------- Bron oldidan tayyorlik ----------------
def test_readiness_blocks_unverified_and_explains_what_is_missing():
    owner, _ = make_user()
    car = make_car(owner)
    c, u = make_user(verified=False)
    r = c.get(f"/api/bookings/readiness?car_id={car['id']}").json()
    assert r["ready"] is False and r["missing"] == ["contact"]
    item = next(i for i in r["items"] if i["code"] == "contact")
    assert item["required"] and item["link"] == "/settings.html#verify"
    assert {i["code"] for i in r["items"]} >= {"name", "phone", "contact", "docs", "region", "card", "avatar"}
    b = c.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(5), "end_date": d(6)})
    assert b.status_code == 403 and "tasdiqlash" in b.json()["detail"]
    with get_db() as db:
        db.execute("UPDATE users SET email_verified = 1 WHERE id = ?", (u["id"],))
    assert c.get(f"/api/bookings/readiness?car_id={car['id']}").json()["ready"] is True
    assert c.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(5), "end_date": d(6)}).status_code == 201


def test_readiness_marks_docs_required_only_for_cars_that_need_them():
    owner, _ = make_user()
    strict = make_car(owner, require_docs=True)
    c, _ = make_user()
    r = c.get(f"/api/bookings/readiness?car_id={strict['id']}").json()
    assert r["missing"] == ["docs"]
    r2 = c.get("/api/bookings/readiness").json()
    assert r2["ready"] is True and not next(i for i in r2["items"] if i["code"] == "docs")["required"]


# ---------------- Admin foydalanuvchini boshqaradi ----------------
def test_admin_edits_profile_and_user_is_notified():
    admin, _ = make_user("admin")
    c, u = make_user()
    r = admin.put(f"/api/admin/users/{u['id']}/profile", headers=H, json={
        "full_name": "Tuzatilgan Ism", "email": "fixed." + u["email"], "phone": "+998 90 777 66 55",
        "region": "Toshkent shahri", "district": "Yunusobod", "lang": "ru", "show_phone": False, "reason": "telefon orqali so'radi"})
    assert r.status_code == 200, r.text
    assert set(r.json()["changed"]) >= {"full_name", "email", "phone", "district", "lang", "show_phone"}
    me = c.get("/api/auth/me").json()["user"]
    assert me["full_name"] == "Tuzatilgan Ism" and me["email"] == "fixed." + u["email"] and me["email_verified"] is False
    assert any(n["type"] == "profile_changed_admin" for n in c.get("/api/notifications").json()["items"])
    detail = admin.get(f"/api/admin/users/{u['id']}").json()
    assert any("[profile]" in n["body"] for n in detail["notes"]) and "readiness" in detail
    # band email boshqa foydalanuvchiga berilmaydi
    other, ou = make_user()
    assert admin.put(f"/api/admin/users/{ou['id']}/profile", headers=H, json={
        "full_name": "X Y", "email": "fixed." + u["email"]}).status_code == 409
    # admin akkauntini bu yo'l bilan o'zgartirib bo'lmaydi
    admin2, a2 = make_user("admin")
    assert admin.put(f"/api/admin/users/{a2['id']}/profile", headers=H, json={"full_name": "A B", "email": "zz@t.uz"}).status_code == 400


def test_admin_temp_password_forces_change():
    admin, _ = make_user("admin")
    c, u = make_user()
    r = admin.post(f"/api/admin/users/{u['id']}/password", headers=H, json={"mode": "temp"})
    pw = r.json()["password"]
    assert r.status_code == 200 and len(pw) >= 10
    assert c.get("/api/auth/me").json()["user"] is None                       # eski sessiya yopildi
    fresh = TestClient(app)
    login = fresh.post("/api/auth/login", headers=H, json={"email": u["email"], "password": pw})
    assert login.status_code == 200 and login.json()["user"]["must_change_pw"] is True
    ch = fresh.post("/api/auth/change-password", headers=H, json={"old_password": pw, "new_password": "Yangi-parol-2027"})
    assert ch.status_code == 200, ch.text
    assert fresh.get("/api/auth/me").json()["user"]["must_change_pw"] is False
    assert admin.post(f"/api/admin/users/{u['id']}/password", headers=H, json={"mode": "email"}).json()["sent_to"] == u["email"]


def test_admin_uploads_docs_for_user_and_manages_cards():
    admin, _ = make_user("admin")
    c, u = make_user()
    for kind, fields in (("license", {"number": "AF1234567", "categories": "B", "expires_on": d(500)}), ("id_card", {"number": "AD1234567"})):
        r = admin.post(f"/api/admin/users/{u['id']}/documents", headers=H, data={"kind": kind, "approve": "1", **fields},
                       files=[("files", ("a.jpg", jpg(), "image/jpeg"))])
        assert r.status_code == 201, r.text
    assert c.get("/api/me/documents").json()["status"] == "verified"
    det = admin.get(f"/api/admin/users/{u['id']}").json()
    lic = det["docs"]["docs"]["license"]
    assert admin.get(f"/api/files/{lic['files'][0]}").status_code == 200     # admin rasmni ko'radi
    assert admin.delete(f"/api/admin/users/{u['id']}/documents/{lic['id']}", headers=H).json()["status"] != "verified"
    c.post("/api/me/cards", headers=H, json={"number": "8600 0000 0000 0007", "exp": "12/30"})
    card = admin.get(f"/api/admin/users/{u['id']}").json()["cards"][0]
    assert card["first6"] == "860000" and "number" not in card
    assert admin.delete(f"/api/admin/users/{u['id']}/cards/{card['id']}", headers=H).status_code == 200
    assert c.get("/api/me/cards").json()["items"] == []


def test_admin_can_edit_any_listing_owner_notified():
    admin, _ = make_user("admin")
    owner, _ = make_user()
    car = make_car(owner, plate="01A123BC")
    got = admin.get(f"/api/cars/{car['id']}").json()
    assert got["can_edit"] is True and got["is_mine"] is False and got["plate"] == "01A123BC"
    body = {k: got[k] for k in ("brand", "model", "year", "city", "body_type", "seats", "transmission", "fuel", "features", "deposit",
                                "min_days", "max_days", "description", "plate")}
    r = admin.put(f"/api/cars/{car['id']}", headers=H, json={**body, "price_per_day": 280000, "delivery_price": None})
    assert r.status_code == 200, r.text
    assert r.json()["price_per_day"] == 280000
    assert any(n["type"] == "car_edited_admin" for n in owner.get("/api/notifications").json()["items"])
    stranger, _ = make_user()
    assert stranger.put(f"/api/cars/{car['id']}", headers=H, json={**body, "price_per_day": 1}).status_code in (400, 403, 422)


# ---------------- Hisobotlar: har bir qism batafsil ochiladi ----------------
def test_report_parts_drill_for_every_role():
    admin, _ = make_user("admin")
    owner, _ = make_user()
    car = make_car(owner)
    renter, _ = make_user()
    b = renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(1), "end_date": d(2)}).json()
    owner.post(f"/api/bookings/{b['id']}/approve", headers=H)
    frm, to = d(-30), d(30)
    for who, scope in ((owner, "owner"), (renter, "renter"), (admin, "admin")):
        rep = who.get(f"/api/analytics/{scope}?from={frm}&to={to}").json()
        assert "funnel" in rep["tables"] and sum(rep["tables"]["funnel"].values()) >= (0 if scope == "admin" else 1)
        specs = [{"entity": "bookings", "status": "done"}, {"entity": "bookings", "status": "pending"},
                 {"entity": "bookings", "status": "cancelled,rejected", "date_field": "created"},
                 {"entity": "bookings", "car_id": car["id"]}, {"entity": "payments", "status": "refunded,refund_pending", "date_field": "cancelled"}]
        if scope != "renter":
            specs += [{"entity": "cars"}, {"entity": "reviews"}]
        if scope == "admin":
            specs += [{"entity": "users"}, {"entity": "payouts"}, {"entity": "bookings", "city": car["city"], "status": "done"}]
        for sp in specs:
            r = who.get("/api/drill", params={"scope": scope, "from": frm, "to": to, **sp})
            assert r.status_code == 200, (scope, sp, r.text)
        own = who.get("/api/drill", params={"scope": scope, "entity": "bookings", "car_id": car["id"], "from": frm, "to": to}).json()
        assert [x["id"] for x in own["items"]] == [b["id"]]
    assert renter.get("/api/drill", params={"scope": "admin", "entity": "users"}).status_code == 403


# ---------------- Maslahatchi: arzon variant ----------------
def test_advisor_prefers_cheaper_among_equals_and_shows_saving():
    owner, _ = make_user()
    city = "Jizzax"
    with get_db() as db:
        db.execute("UPDATE cars SET is_active = 0 WHERE city = ?", (city,))
    pricey = make_car(owner, brand="Chevrolet", model="Malibu", city=city, price_per_day=700_000, features=["ac", "usb"])
    cheap = make_car(owner, brand="Chevrolet", model="Cobalt", city=city, price_per_day=300_000, features=["ac", "usb"])
    r = TestClient(app).post("/api/advisor", headers=H, json={"purpose": "city", "passengers": 2, "city": city,
                                                              "start_date": d(3), "end_date": d(5)}).json()
    ids = [x["id"] for x in r["items"]]
    assert ids.index(cheap["id"]) < ids.index(pricey["id"])
    first = r["items"][0]
    assert any(p["code"] in ("below_market", "cheapest_city") for p in first["pros"])
    assert {t["code"] for t in r["save_tips"]} >= {"save_compare", "save_deposit"}
    assert first["badge"] in ("best_match", "best_price")


# ---------------- Gmail ko'prigi (Render SMTP portlarini yopgan) ----------------
def test_email_relay_follows_redirect_and_reports_errors(monkeypatch):
    import json as _json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from app import channels
    from app.config import settings
    got = {}

    class H_(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):   # Apps Script kabi: POST qabul qilib, natija sahifasiga 302
            got.update(_json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(302)
            self.send_header("Location", "/result?ok=" + ("1" if got["token"] == "sir" else "0"))
            self.end_headers()

        def do_GET(self):
            ok_ = self.path.endswith("=1")
            body = _json.dumps({"ok": ok_} if ok_ else {"ok": False, "error": "token"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

    srv = HTTPServer(("127.0.0.1", 0), H_)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(settings, "EMAIL_RELAY_URL", f"http://127.0.0.1:{srv.server_port}/exec")
    monkeypatch.setattr(settings, "EMAIL_RELAY_TOKEN", "sir")
    try:
        assert settings.email_enabled
        assert channels._email_send("a@b.uz", "Kod", "123456")["status"] == "sent"
        assert got["to"] == "a@b.uz" and got["body"] == "123456"
        monkeypatch.setattr(settings, "EMAIL_RELAY_TOKEN", "xato")
        r = channels._email_send("a@b.uz", "Kod", "1")
        assert r["status"] == "failed" and "token" in r["error"]
    finally:
        srv.shutdown()
