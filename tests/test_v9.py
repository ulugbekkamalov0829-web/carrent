"""v9: uzoq muddat chegirmasi, davlat raqami majburiy, JSHSHIR tekshiruvi, barmoq izi (passkey), ADMIN_EMAILS."""
import base64
import hashlib
import json
import struct
from datetime import date, timedelta

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from app.config import settings
from app.db import get_db
from conftest import CAR, H, make_car, make_user


def d(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


def test_long_rental_discount_in_quote_and_booking():
    owner, _ = make_user()
    car = make_car(owner, price_per_day=100000, discounts={"3": 5, "7": 10, "30": 20}, fuel_per_100=7.5, delivery_price=None)
    assert car["discounts"] == {"3": 5, "7": 10, "30": 20} and car["fuel_per_100"] == 7.5
    renter, _ = make_user()
    q = renter.get(f"/api/cars/{car['id']}/quote", params={"start": d(3), "end": d(4)}).json()
    assert q["discount_pct"] == 0 and q["total"] == 200000
    q = renter.get(f"/api/cars/{car['id']}/quote", params={"start": d(3), "end": d(9)}).json()   # 7 kun
    assert q["discount_pct"] == 10 and q["rent_full"] == 700000 and q["discount"] == 70000 and q["total"] == 630000
    b = renter.post("/api/bookings", headers=H, json={"car_id": car["id"], "start_date": d(3), "end_date": d(9)})
    assert b.status_code == 201, b.text
    assert b.json()["total_price"] == 630000
    bad = owner.post("/api/cars", headers=H, json={**CAR, "discounts": {"5": 10}})
    assert bad.status_code == 422


def test_plate_required_and_tech_passport_private():
    owner, _ = make_user()
    body = {k: v for k, v in CAR.items() if k != "plate"}
    assert owner.post("/api/cars", headers=H, json=body).status_code == 422
    car = make_car(owner, tech_passport="aaf 1234567")
    assert owner.get(f"/api/cars/{car['id']}").json()["tech_passport"] == "AAF1234567"
    other, _ = make_user()
    got = other.get(f"/api/cars/{car['id']}").json()
    assert "tech_passport" not in got and "plate" not in got


def test_pinfl_identity_check():
    c, _ = make_user()
    bad = c.put("/api/me/identity", headers=H, json={"pinfl": "12345678901234", "passport": "AA1234567"})
    assert bad.status_code == 400
    bad = c.put("/api/me/identity", headers=H, json={"pinfl": "33113990010012", "passport": "AA1234567"})  # 31.13 — yo'q sana
    assert bad.status_code == 400
    r = c.put("/api/me/identity", headers=H, json={"pinfl": "31505900010012", "passport": "aa 1234567"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["birth_date"] == "1990-05-15" and j["gender"] == "m" and j["identity_status"] == "checked"
    assert "0010012" not in json.dumps(j) and j["pinfl_mask"].endswith("0012")
    other, _ = make_user()
    dup = other.put("/api/me/identity", headers=H, json={"pinfl": "31505900010012", "passport": "AB7654321"})
    assert dup.status_code == 409
    # bittasi yetarli: faqat pasport
    third, _ = make_user()
    r = third.put("/api/me/identity", headers=H, json={"passport": "ae 7654321"})
    assert r.status_code == 200 and r.json()["passport_mask"].startswith("AE")
    assert other.put("/api/me/identity", headers=H, json={"passport": "AE7654321"}).status_code == 409
    assert other.put("/api/me/identity", headers=H, json={}).status_code == 400


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _cbor_bytes(b: bytes) -> bytes:
    return (bytes([0x58, len(b)]) if len(b) < 256 else bytes([0x59]) + struct.pack(">H", len(b))) + b


def test_passkey_register_and_login():
    c, u = make_user()
    key = ec.generate_private_key(ec.SECP256R1())
    nums = key.public_key().public_numbers()
    x, y = nums.x.to_bytes(32, "big"), nums.y.to_bytes(32, "big")
    # COSE kalit: {1: 2, 3: -7, -1: 1, -2: x, -3: y}
    cose = bytes([0xa5, 0x01, 0x02, 0x03, 0x26, 0x20, 0x01, 0x21]) + _cbor_bytes(x) + bytes([0x22]) + _cbor_bytes(y)
    opts = c.post("/api/passkeys/register/options", headers=H).json()
    assert opts["rp"]["id"] == "testserver"
    cred_id = b"cred-123456"
    rp_hash = hashlib.sha256(b"testserver").digest()
    auth = rp_hash + bytes([0x45]) + struct.pack(">I", 1) + bytes(16) + struct.pack(">H", len(cred_id)) + cred_id + cose
    att = bytes([0xa3, 0x63]) + b"fmt" + bytes([0x64]) + b"none" + bytes([0x67]) + b"attStmt" + bytes([0xa0]) \
        + bytes([0x68]) + b"authData" + _cbor_bytes(auth)
    cd = json.dumps({"type": "webauthn.create", "challenge": opts["challenge"], "origin": "https://testserver"}).encode()
    r = c.post("/api/passkeys/register", headers=H, json={"id": _b64(cred_id), "clientDataJSON": _b64(cd),
                                                          "attestationObject": _b64(att), "name": "Telefon"})
    assert r.status_code == 201, r.text
    assert len(c.get("/api/passkeys").json()["items"]) == 1

    from starlette.testclient import TestClient
    from app.main import app
    anon = TestClient(app)
    lo = anon.post("/api/passkeys/login/options", headers=H).json()
    cd2 = json.dumps({"type": "webauthn.get", "challenge": lo["challenge"], "origin": "https://testserver"}).encode()
    auth2 = rp_hash + bytes([0x05]) + struct.pack(">I", 2)
    sig = key.sign(auth2 + hashlib.sha256(cd2).digest(), ec.ECDSA(hashes.SHA256()))
    r = anon.post("/api/passkeys/login", headers=H, json={"id": _b64(cred_id), "clientDataJSON": _b64(cd2),
                                                          "authenticatorData": _b64(auth2), "signature": _b64(sig)})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["id"] == u["id"]
    assert anon.get("/api/auth/me").json()["user"]["id"] == u["id"]
    # takroriy (eski challenge bilan) urinish rad etiladi
    r = anon.post("/api/passkeys/login", headers=H, json={"id": _b64(cred_id), "clientDataJSON": _b64(cd2),
                                                          "authenticatorData": _b64(auth2), "signature": _b64(sig)})
    assert r.status_code == 400


def test_admin_emails_promote_after_verification():
    c, u = make_user(verified=False)
    settings.ADMIN_EMAILS = {u["email"].lower()}
    try:
        assert c.get("/api/auth/me").json()["user"]["role"] == "user"
        with get_db() as db:
            db.execute("UPDATE users SET email_verified = 1 WHERE id = ?", (u["id"],))
        r = c.post("/api/auth/login", headers=H, json={"login": u["email"], "password": "Uzun-parol-2026"})
        assert r.status_code == 200 and r.json()["user"]["role"] == "admin"
    finally:
        settings.ADMIN_EMAILS = set()


def test_app_pin_lock_and_lockout():
    c, u = make_user()
    dev = "dev_" + "a" * 20
    assert c.get("/api/me/pin", params={"device_id": dev}).json()["set"] is False
    assert c.put("/api/me/pin", headers=H, json={"device_id": dev, "pin": "1111"}).status_code == 400   # oson
    assert c.put("/api/me/pin", headers=H, json={"device_id": dev, "pin": "1234"}).status_code == 400
    assert c.put("/api/me/pin", headers=H, json={"device_id": dev, "pin": "4827"}).status_code == 200
    assert c.post("/api/me/pin/verify", headers=H, json={"device_id": dev, "pin": "4827"}).json()["unlocked"] is True
    for i in range(4):
        r = c.post("/api/me/pin/verify", headers=H, json={"device_id": dev, "pin": "0000"})
        assert r.status_code == 401
    r = c.post("/api/me/pin/verify", headers=H, json={"device_id": dev, "pin": "0000"})
    assert r.status_code == 403 and r.json()["locked_out"] is True
    assert c.get("/api/auth/me").json()["user"] is None          # sessiya yopildi


def test_web_login_is_session_cookie_app_login_persistent():
    from starlette.testclient import TestClient
    from app.main import app
    _, u = make_user()
    web = TestClient(app)
    r = web.post("/api/auth/login", headers=H, json={"login": u["email"], "password": "Uzun-parol-2026"})
    assert "Max-Age" not in r.headers["set-cookie"]
    appc = TestClient(app)
    r = appc.post("/api/auth/login", headers={**H, "X-App-Mode": "app"}, json={"login": u["email"], "password": "Uzun-parol-2026"})
    assert "Max-Age" in r.headers["set-cookie"]
