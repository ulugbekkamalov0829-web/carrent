import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="carrent_test_")
os.environ["DATA_DIR"] = _tmp
os.environ["DB_PATH"] = str(Path(_tmp) / "test.db")
os.environ["UPLOAD_DIR"] = str(Path(_tmp) / "uploads")
os.environ["REGISTER_PER_HOUR"] = "100000"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-only-0123456789"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app.db import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.security import hash_password  # noqa: E402

H = {"X-Requested-With": "fetch"}
PASSWORD = "Uzun-parol-2026"


@pytest.fixture(scope="session", autouse=True)
def _app():
    with TestClient(app) as c:  # lifespan -> init_db
        yield c


@pytest.fixture
def client():
    return TestClient(app)


_counter = {"n": 0}


def make_user(role: str = "user", verified: bool = True) -> tuple[TestClient, dict]:
    _counter["n"] += 1
    c = TestClient(app)
    email = f"{role}{_counter['n']}@t.uz"
    if role == "admin":
        with get_db() as db:
            db.execute("INSERT INTO users (full_name, email, phone, password_hash, role) VALUES (?, ?, '', ?, 'admin')",
                       ("Admin Test", email, hash_password(PASSWORD)))
        r = c.post("/api/auth/login", json={"email": email, "password": PASSWORD}, headers=H)
    else:
        r = c.post("/api/auth/register", headers=H, json={
            "full_name": f"User Test {_counter['n']}", "email": email, "phone": f"+99877{_counter['n']:07d}",
            "password": PASSWORD, "accept_terms": True, "region": "Toshkent shahri", "district": "Chilonzor"})
    assert r.status_code in (200, 201), r.text
    if role != "admin" and verified:
        # Bron qilish uchun email tasdiqlangan bo'lishi kerak — testlarda tayyor holatdan boshlaymiz
        with get_db() as db:
            db.execute("UPDATE users SET email_verified = 1 WHERE email = ?", (email,))
    return c, r.json()["user"]


CAR = {"brand": "Chevrolet", "model": "Cobalt", "year": 2023, "city": "Toshkent", "body_type": "sedan", "seats": 5,
       "transmission": "automatic", "fuel": "petrol", "features": ["ac", "usb"], "price_per_day": 300000,
       "deposit": 500000, "min_days": 1, "max_days": 30, "delivery_price": 50000, "description": "Test", "plate": "01A123BC"}


def make_car(owner_client: TestClient, **overrides) -> dict:
    r = owner_client.post("/api/cars", json={**CAR, **overrides}, headers=H)
    assert r.status_code == 201, r.text
    return r.json()
