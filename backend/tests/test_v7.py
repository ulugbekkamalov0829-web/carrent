"""v7: kartalar, hujjatlar, maxfiy fayllar, hisobni o'chirish, adminlar, parol tiklash 2 qadami,
elektron shartnoma, qabul-topshirish dalolatnomasi, xabarda joylashuv, mashina joylashuvi maxfiyligi."""
import io
import re
from datetime import date, timedelta

from PIL import Image
from starlette.testclient import TestClient

from app.db import get_db
from app.main import app
from conftest import H, PASSWORD, make_car, make_user


def d(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


def jpg(color=(200, 30, 30)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(b, "JPEG")
    return b.getvalue()


def last_code(to: str) -> str:
    with get_db() as db:
        row = db.execute("SELECT body FROM dev_outbox WHERE to_addr = ? ORDER BY id DESC LIMIT 1", (to,)).fetchone()
    return re.findall(r"\b(\d{6})\b", row[0])[-1]


def upload_doc(c, kind, **fields):
    files = [("files", (f"{kind}.jpg", jpg(), "image/jpeg"))]
    return c.post("/api/me/documents", headers=H, data={"kind": kind, **fields}, files=files)


def verify_docs(user_client, admin):
    upload_doc(user_client, "license", number="AF1234567", categories="B, C", expires_on=d(800))
    upload_doc(user_client, "id_card", number="AD7654321")
    for x in admin.get("/api/admin/documents?status=pending").json()["items"]:
        admin.post(f"/api/admin/documents/{x['id']}/review", headers=H, json={"approve": True})


# ---------------- Kartalar ----------------
def test_cards_store_only_masked_number():
    c, u = make_user()
    assert c.post("/api/me/cards", headers=H, json={"number": "8600 1234 5678 9013", "exp": "12/30"}).status_code == 400   # Luhn
    r = c.post("/api/me/cards", headers=H, json={"number": "8600 0000 0000 0007", "exp": "12/30", "holder": "Ali Valiyev"})
    assert r.status_code == 200
    card = r.json()["items"][0]
    assert card["brand"] == "uzcard" and card["first6"] == "860000" and card["last4"] == "0007" and card["is_default"] == 1
    assert c.post("/api/me/cards", headers=H, json={"number": "4111111111111111", "exp": "01/20"}).status_code == 400   # muddati o'tgan
    with get_db() as db:
        stored = " ".join(str(v) for row in db.execute("SELECT * FROM user_cards").fetchall() for v in row)
    assert "8600000000000007" not in stored
    c.post("/api/me/cards", headers=H, json={"number": "4111 1111 1111 1111", "exp": "05/31"})
    items = c.get("/api/me/cards").json()["items"]
    visa = next(x for x in items if x["brand"] == "visa")
    c.post(f"/api/me/cards/{visa['id']}/default", headers=H)
    assert [x["brand"] for x in c.get("/api/me/cards").json()["items"] if x["is_default"]] == ["visa"]


# ---------------- Hujjatlar va maxfiy fayllar ----------------
def test_documents_review_gate_booking_and_private_files():
    owner, _ = make_user()
    renter, r = make_user()
    stranger, _ = make_user()
    admin, _ = make_user("admin")
    car = make_car(owner, require_docs=True)
    res = renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(3), "end_date": d(4)})
    assert res.status_code == 403
    assert upload_doc(renter, "license", number="AF1234567").status_code == 400              # toifa va muddat yo'q
    up = upload_doc(renter, "license", number="AF 1234567", categories="B", expires_on=d(500))
    assert up.status_code == 201 and up.json()["status"] == "pending"
    lic = up.json()["docs"]["license"]
    assert lic["number_mask"] == "AF ***567"
    f = lic["files"][0]
    assert renter.get(f"/api/files/{f}").status_code == 200
    assert stranger.get(f"/api/files/{f}").status_code == 404
    assert owner.get(f"/api/files/{f}").status_code == 404
    assert admin.get(f"/api/files/{f}").status_code == 200
    assert TestClient(app).get(f"/uploads/{f}").status_code == 404                           # ochiq papkada yo'q
    verify_docs(renter, admin)
    assert renter.get("/api/me/documents").json()["status"] == "verified"
    assert renter.get("/api/auth/me").json()["user"]["docs_status"] == "verified"
    b = renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(3), "end_date": d(4)})
    assert b.status_code == 201
    inc = owner.get("/api/bookings/incoming").json()["items"][0]
    assert inc["renter_docs_verified"] == 1
    # Rad etish sababi bilan
    upload_doc(stranger, "id_card", number="AB1112223")
    x = next(i for i in admin.get("/api/admin/documents").json()["items"] if i["user_id"] != r["id"])
    assert admin.post(f"/api/admin/documents/{x['id']}/review", headers=H, json={"approve": False}).status_code == 400
    assert admin.post(f"/api/admin/documents/{x['id']}/review", headers=H, json={"approve": False, "reason": "Surat xira"}).status_code == 200
    assert stranger.get("/api/me/documents").json()["docs"]["id_card"]["reject_reason"] == "Surat xira"


# ---------------- Hisobni o'chirish va adminlar ----------------
def test_delete_account_frees_email_for_reuse():
    c, u = make_user()
    make_car(c)
    r = c.post("/api/me/delete", headers=H, json={"password": PASSWORD})
    assert r.status_code == 200 and r.json()["mode"] == "deleted"
    with get_db() as db:
        assert not db.execute("SELECT 1 FROM users WHERE id = ?", (u["id"],)).fetchone()
        assert not db.execute("SELECT 1 FROM cars WHERE owner_id = ?", (u["id"],)).fetchone()
    again = TestClient(app).post("/api/auth/register", headers=H, json={
        "full_name": "Qayta Foydalanuvchi", "email": u["email"], "phone": u["phone"], "password": PASSWORD, "accept_terms": True,
        "region": "Toshkent shahri", "district": "Chilonzor"})
    assert again.status_code == 201


def test_admin_roles_and_erase():
    admin, a = make_user("admin")
    c, u = make_user()
    assert admin.post(f"/api/admin/users/{a['id']}/role", headers=H, json={"role": "user"}).status_code == 400   # o'zini emas
    assert admin.post(f"/api/admin/users/{u['id']}/role", headers=H, json={"role": "admin"}).status_code == 200
    assert c.get("/api/admin/stats").status_code == 401                                         # sessiya yopildi
    c2 = TestClient(app)
    assert c2.post("/api/auth/login", headers=H, json={"email": u["email"], "password": PASSWORD}).json()["user"]["role"] == "admin"
    assert c2.get("/api/admin/stats").status_code == 200
    assert admin.post(f"/api/admin/users/{u['id']}/role", headers=H, json={"role": "user"}).status_code == 200
    victim, v = make_user()
    assert admin.post(f"/api/admin/users/{v['id']}/erase", headers=H).json()["mode"] == "deleted"
    assert c.post(f"/api/admin/users/{a['id']}/erase", headers=H).status_code in (401, 403)


# ---------------- Parolni tiklash: avval kod tekshiriladi ----------------
def test_reset_check_then_new_password():
    _, u = make_user()
    pub = TestClient(app)
    pub.post("/api/auth/forgot", headers=H, json={"login": u["email"]})
    code = last_code(u["email"])
    assert pub.post("/api/auth/reset/check", headers=H, json={"login": u["email"], "code": "000000" if code != "000000" else "111111"}).status_code == 400
    assert pub.post("/api/auth/reset/check", headers=H, json={"login": u["email"], "code": code}).json() == {"valid": True}
    # Tekshiruv kodni "ishlatmaydi": yangi parol shu kod bilan o'rnatiladi
    r = pub.post("/api/auth/reset", headers=H, json={"login": u["email"], "code": code, "new_password": "Yangi-Parol-2026!"})
    assert r.status_code == 200


# ---------------- Elektron shartnoma ----------------
def _approved_booking(start=1, end=3, **car_kw):
    owner, o = make_user()
    renter, r = make_user()
    car = make_car(owner, plate="01A123BC", **car_kw)
    b = renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(start), "end_date": d(end)}).json()
    owner.post(f"/api/bookings/{b['id']}/approve", headers=H)
    return owner, o, renter, r, car, b


def test_contract_sign_approve_verify():
    owner, o, renter, r, car, b = _approved_booking()
    admin, _ = make_user("admin")
    stranger, _ = make_user()
    c = renter.get(f"/api/bookings/{b['id']}/contract").json()
    assert c["status"] == "pending" and c["can_sign"] and "01A123BC" in c["body"] and r["full_name"] in c["body"] and c["intact"]
    assert stranger.get(f"/api/bookings/{b['id']}/contract").status_code == 403
    assert admin.post(f"/api/admin/contracts/{c['id']}/approve", headers=H).status_code == 400   # hali imzolanmagan
    for client, user in ((renter, r), (owner, o)):
        assert client.post(f"/api/contracts/{c['id']}/sign", headers=H, json={"code": "123456", "agree": True}).status_code == 400
        client.post(f"/api/contracts/{c['id']}/sign/start", headers=H)
        code = last_code(user["email"])
        assert client.post(f"/api/contracts/{c['id']}/sign", headers=H, json={"code": code, "agree": False}).status_code == 400
        res = client.post(f"/api/contracts/{c['id']}/sign", headers=H, json={"code": code, "agree": True}).json()
        assert not res["can_sign"]
    assert res["status"] == "signed"
    assert admin.post(f"/api/admin/contracts/{c['id']}/approve", headers=H).status_code == 200
    c = owner.get(f"/api/bookings/{b['id']}/contract").json()
    assert c["status"] == "approved" and c["approved_by"]
    n, tok = re.search(r"n=([^&]+)&t=(.+)$", c["verify_path"]).groups()
    v = TestClient(app).get(f"/api/contracts/verify?n={n}&t={tok}").json()
    assert v["status"] == "approved" and v["intact"] and r["full_name"] not in str(v)                 # ochiq sahifada to'liq ism yo'q
    assert TestClient(app).get(f"/api/contracts/verify?n={n}&t=wrong").status_code == 404
    # Matn o'zgartirilsa — tekshiruv buni ko'rsatadi
    with get_db() as db:
        db.execute("UPDATE contracts SET body = body || ' ' WHERE id = ?", (c["id"],))
    assert TestClient(app).get(f"/api/contracts/verify?n={n}&t={tok}").json()["intact"] is False


def test_contract_template_editable():
    admin, _ = make_user("admin")
    tpl = admin.get("/api/admin/contract-template").json()
    assert tpl["is_default"] and "{renter_name}" in tpl["template"]
    assert admin.put("/api/admin/contract-template", headers=H, json={"template": "# Qisqa " + "x" * 300}).status_code == 400
    custom = tpl["template"].replace("## 12. Tomonlar ma'lumotlari", "## 12. Maxsus band\n12.1. Mashinada chekish taqiqlanadi.\n## 13. Tomonlar ma'lumotlari")
    assert admin.put("/api/admin/contract-template", headers=H, json={"template": custom}).status_code == 200
    owner, o, renter, r, car, b = _approved_booking()
    assert "Mashinada chekish taqiqlanadi" in renter.get(f"/api/bookings/{b['id']}/contract").json()["body"]
    admin.put("/api/admin/contract-template", headers=H, json={"template": tpl["default"]})


# ---------------- Qabul-topshirish dalolatnomasi ----------------
def _act(client, bid, kind, odo, fuel, damage=False, notes=""):
    files = [("photos", (f"p{i}.jpg", jpg((i * 40, 80, 120)), "image/jpeg")) for i in range(4)]
    return client.post(f"/api/bookings/{bid}/handover", headers=H, files=files,
                       data={"kind": kind, "odometer_km": str(odo), "fuel_pct": str(fuel), "clean": "1", "damage": "1" if damage else "0", "notes": notes})


def test_handover_flow_and_charges():
    owner, o, renter, r, car, b = _approved_booking(1, 2, km_limit=100, extra_km_price=2000, tank_l=50, fuel_price=12000, fuel_policy="same")
    stranger, _ = make_user()
    assert _act(renter, b["id"], "return", 1000, 50).status_code == 400                              # avval topshirish
    one = renter.post(f"/api/bookings/{b['id']}/handover", headers=H, files=[("photos", ("a.jpg", jpg(), "image/jpeg"))],
                      data={"kind": "pickup", "odometer_km": "1000", "fuel_pct": "80"})
    assert one.status_code == 400                                                                   # kamida 4 surat
    assert _act(stranger, b["id"], "pickup", 1000, 80).status_code == 403
    p = _act(owner, b["id"], "pickup", 10_000, 80)
    assert p.status_code == 201 and len(p.json()["pickup"]["photos"]) == 4
    photo = p.json()["pickup"]["photos"][0]
    assert renter.get(photo).status_code == 200 and stranger.get(photo).status_code == 404
    assert owner.post(f"/api/bookings/{b['id']}/handover/pickup/confirm", headers=H, json={"agree": True}).status_code == 403  # o'zi emas
    assert renter.post(f"/api/bookings/{b['id']}/handover/pickup/confirm", headers=H, json={"agree": True}).status_code == 400  # hujjatlar tekshirilmagan
    assert renter.post(f"/api/bookings/{b['id']}/handover/pickup/confirm", headers=H, json={"agree": True, "docs_checked": True}).status_code == 200
    assert _act(renter, b["id"], "return", 9_000, 50).status_code == 400                               # probeg kamaymaydi
    ret = _act(renter, b["id"], "return", 10_350, 50, damage=True, notes="Old bamperda yangi tirnalish")
    calc = ret.json()["calc"]
    # 2 kun × 100 km = 200 km ruxsat; 350 yurildi -> 150 km × 2000 = 300 000; yoqilg'i 30% × 50 l = 15 l × 12 000 = 180 000
    assert (calc["km_used"], calc["km_over"], calc["km_charge"]) == (350, 150, 300_000)
    assert (calc["fuel_short_pct"], calc["fuel_liters"], calc["fuel_charge"]) == (30, 15.0, 180_000)
    assert calc["total"] == 480_000 and calc["new_damage"] and calc["from_deposit"] == 480_000
    o_conf = owner.post(f"/api/bookings/{b['id']}/handover/return/confirm", headers=H, json={"agree": False, "objection": "Yoqilg'i 40% edi"})
    assert o_conf.json()["return"]["objection"] == "Yoqilg'i 40% edi"


# ---------------- Joylashuv ----------------
def test_location_message_and_car_location_privacy():
    owner, o = make_user()
    renter, r = make_user()
    car = make_car(owner, lat=41.2995, lng=69.2401, address="Chilonzor 12-mavze, 5-uy")
    pub = renter.get(f"/api/cars/{car['id']}").json()
    assert pub["loc_exact"] is False and pub["address"] is None and pub["lat"] == 41.3
    mine = owner.get(f"/api/cars/{car['id']}").json()
    assert mine["loc_exact"] and mine["lat"] == 41.2995 and mine["address"].startswith("Chilonzor")
    b = renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(2), "end_date": d(3)}).json()
    owner.post(f"/api/bookings/{b['id']}/approve", headers=H)
    assert renter.get(f"/api/cars/{car['id']}").json()["lat"] == 41.2995
    bad = owner.post("/api/cars", headers=H, json={**{k: v for k, v in car.items() if k in ("brand", "model", "year", "body_type", "seats", "transmission", "fuel", "price_per_day")},
                                                   "city": "Toshkent", "lat": 10.0, "lng": 69.2})
    assert bad.status_code == 422
    assert renter.post("/api/messages", headers=H, json={"to_user_id": o["id"], "body": "Shu yerdaman", "kind": "location"}).status_code == 422
    m = renter.post("/api/messages", headers=H, json={"to_user_id": o["id"], "body": "Shu yerdaman", "kind": "location", "lat": 41.31, "lng": 69.28})
    assert m.status_code == 201
    th = owner.get(f"/api/messages/{r['id']}").json()["items"][-1]
    assert th["kind"] == "location" and th["lat"] == 41.31
