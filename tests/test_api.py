"""CarRent biznes qoidalari va xavfsizlik testlari.  Ishga tushirish:  pytest -q"""
import ast
import threading
from datetime import date, timedelta
from pathlib import Path

from starlette.testclient import TestClient

from app.db import get_db
from app.i18n import CATALOG
from app.main import app
from conftest import CAR, H, PASSWORD, make_car, make_user


def d(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


def book(c, car_id, s, e, **kw):
    return c.post("/api/bookings", headers=H, json={"car_id": car_id, "start_date": d(s), "end_date": d(e), **kw})


def finish(booking_id):
    """Vaqtni 'o'tkazish': bronni o'tmishda tugagan qilib qo'yamiz."""
    with get_db() as db:
        db.execute("UPDATE bookings SET start_date = ?, end_date = ? WHERE id = ?", (d(-5), d(-3), booking_id))


# ---------------- Autentifikatsiya ----------------
def test_register_login_logout(client):
    r = client.post("/api/auth/register", headers=H, json={
        "full_name": "Ali Valiyev", "email": "Ali@Test.uz", "phone": "+998901112233", "password": PASSWORD,
        "accept_terms": True, "lang": "ru", "region": "Namangan", "district": "Chust"})
    assert r.status_code == 201
    u = r.json()["user"]
    assert u["email"] == "ali@test.uz" and u["role"] == "user" and u["lang"] == "ru" and "password_hash" not in u
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    client.post("/api/auth/logout", headers=H)
    client.cookies.clear()
    assert client.get("/api/auth/me").json()["user"] is None
    assert client.post("/api/auth/login", headers=H, json={"email": "ali@test.uz", "password": PASSWORD}).status_code == 200


def test_password_policy_and_terms(client):
    base = {"full_name": "Test User", "email": "pw@t.uz", "phone": "+998935550000", "accept_terms": True,
            "region": "Samarqand", "district": "Urgut"}
    assert client.post("/api/auth/register", headers=H, json={**base, "password": "qisqa123"}).status_code == 422
    assert client.post("/api/auth/register", headers=H, json={**base, "password": "qwerty123456"}).status_code == 422
    assert client.post("/api/auth/register", headers=H, json={**base, "password": "Pw-parolim-2026"}).status_code == 422  # emailni o'z ichiga oladi
    for weak in ("kichik-harf-2026", "KATTA-HARF-2026", "Raqamsiz-parol", "Belgisiz2026Parol", "Qs-1"):   # har bir qoida alohida
        r = client.post("/api/auth/register", headers=H, json={**base, "password": weak})
        assert r.status_code == 422, weak
    assert client.post("/api/auth/register", headers=H, json={**base, "password": PASSWORD, "accept_terms": False}).status_code == 422
    # barcha qoidalarga mos parol (bo'shliqli ibora ham bo'ladi) qabul qilinadi
    assert client.post("/api/auth/register", headers=H, json={**base, "password": "Men ertaga Samarqandga 2 kunga!"}).status_code == 201


def test_cannot_register_as_admin(client):
    r = client.post("/api/auth/register", headers=H, json={"full_name": "Hacker", "email": "h@t.uz", "phone": "+998901112233",
                                                            "password": PASSWORD, "accept_terms": True, "role": "admin"})
    assert r.status_code == 422


def test_login_rate_limit(client):
    for _ in range(8):
        assert client.post("/api/auth/login", json={"email": "x@t.uz", "password": "wrong"}, headers=H).status_code == 401
    assert client.post("/api/auth/login", json={"email": "x@t.uz", "password": "wrong"}, headers=H).status_code == 429


def test_csrf_and_security_headers(client):
    assert client.post("/api/auth/login", json={"email": "a@a.uz", "password": "x"}).status_code == 403
    r = client.get("/api/health")
    assert r.headers["x-frame-options"] == "DENY" and "default-src 'self'" in r.headers["content-security-policy"]


# ---------------- Uch til ----------------
def test_server_messages_follow_language(client):
    for lang, word in (("uz", "notoʻgʻri"), ("ru", "Неверный"), ("en", "Invalid")):
        client.cookies.set("lang", lang)
        assert word in client.post("/api/auth/login", json={"email": "no@t.uz", "password": "x"}, headers=H).json()["detail"]
    client.cookies.clear()


def test_every_server_message_is_translated():
    """Kodda tr("...") bilan yozilgan har bir matn uchun ru va en tarjimasi bo'lishi shart."""
    missing = set()
    for py in Path(__file__).resolve().parent.parent.joinpath("app").rglob("*.py"):
        for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr" and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and arg.value not in CATALOG:
                    missing.add(arg.value)
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and getattr(node.exc.func, "id", None) == "ValueError":
                arg = node.exc.args[0] if node.exc.args else None
                if isinstance(arg, ast.Constant) and arg.value not in CATALOG:
                    missing.add(arg.value)
    assert not missing, f"Tarjimasi yo'q: {missing}"


def test_language_saved_for_user():
    c, _ = make_user()
    assert c.patch("/api/me/lang", json={"lang": "en"}, headers=H).status_code == 200
    assert c.get("/api/auth/me").json()["user"]["lang"] == "en"


# ---------------- Bitta akkaunt, ikki rejim ----------------
def test_one_account_can_rent_and_list():
    """Ali bugun Malibu'ni ijaraga oladi, ertaga o'z Cobalt'ini ijaraga beradi — bitta akkaunt bilan."""
    ali, ali_u = make_user()
    owner, _ = make_user()
    malibu = make_car(owner, model="Malibu")
    b = book(ali, malibu["id"], 5, 6)
    assert b.status_code == 201
    cobalt = make_car(ali)                                     # o'sha akkaunt e'lon qo'shadi
    me = ali.get("/api/auth/me").json()["user"]
    assert me["id"] == ali_u["id"] and me["active_mode"] == "owner" and me["cars_count"] == 1
    # Rejim almashtirish ma'lumotni o'zgartirmaydi va idempotent
    for _ in range(3):
        assert ali.patch("/api/me/mode", json={"mode": "renter"}, headers=H).json()["user"]["id"] == ali_u["id"]
    assert [x["id"] for x in ali.get("/api/bookings/mine").json()["items"]] == [b.json()["id"]]
    assert [x["id"] for x in ali.get("/api/my/cars").json()["items"]] == [cobalt["id"]]
    # Ruxsat rejimdan emas, egalikdan: renter rejimida ham o'z e'lonini tahrirlay oladi
    assert ali.put(f"/api/cars/{cobalt['id']}", json={**CAR, "price_per_day": 320000}, headers=H).status_code == 200
    assert ali.patch("/api/me/mode", json={"mode": "admin"}, headers=H).status_code == 422


def test_cannot_book_own_car():
    c, _ = make_user()
    car = make_car(c)
    assert book(c, car["id"], 1, 2).status_code == 400


# ---------------- Egalik va ruxsatlar (IDOR) ----------------
def test_ownership_rules():
    o1, _ = make_user()
    o2, _ = make_user()
    renter, _ = make_user()
    stranger, _ = make_user()
    car = make_car(o1)
    assert o2.put(f"/api/cars/{car['id']}", json=CAR, headers=H).status_code == 403
    assert o2.delete(f"/api/cars/{car['id']}", headers=H).status_code == 403
    b = book(renter, car["id"], 3, 4).json()
    assert o2.post(f"/api/bookings/{b['id']}/approve", headers=H).status_code == 403
    assert stranger.post(f"/api/bookings/{b['id']}/cancel", headers=H).status_code == 403
    assert b["id"] not in [x["id"] for x in stranger.get("/api/bookings/mine").json()["items"]]
    assert b["id"] not in [x["id"] for x in o2.get("/api/bookings/incoming").json()["items"]]
    assert renter.get("/api/admin/stats").status_code == 403
    assert o1.put("/api/admin/settings", json={"commission_percent": 0}, headers=H).status_code == 403


def test_messages_are_private():
    a, au = make_user()
    b, bu = make_user()
    c, _ = make_user()
    a.post("/api/messages", headers=H, json={"to_user_id": bu["id"], "body": "Salom!"})
    assert b.get("/api/me/summary").json()["unread_messages"] == 1
    assert c.get(f"/api/messages/{au['id']}").json()["items"] == []          # begona suhbatni ko'ra olmaydi
    assert b.get(f"/api/messages/{au['id']}").json()["items"][-1]["body"] == "Salom!"
    assert a.post("/api/messages", headers=H, json={"to_user_id": au["id"], "body": "x"}).status_code == 400


# ---------------- Qidiruv ----------------
def test_search_and_filters(client):
    owner, _ = make_user()
    make_car(owner, brand="Filtrbrand", model="Han", city="Xorazm", district="Xiva shahri", price_per_day=1_000_000, fuel="electric", features=["ac", "camera"])
    make_car(owner, brand="Filtrbrand", model="Spark", city="Xorazm", district="Xiva shahri", price_per_day=200_000, transmission="manual", body_type="hatchback")
    hidden = make_car(owner, brand="Filtrbrand", city="Xorazm", district="Xiva shahri", is_active=False)
    r = client.get("/api/cars", params={"brand": "Filtrbrand"}).json()
    assert r["total"] == 2 and hidden["id"] not in [c["id"] for c in r["items"]]
    assert client.get("/api/cars", params={"brand": "Filtrbrand", "fuel": "electric"}).json()["total"] == 1
    assert client.get("/api/cars", params={"brand": "Filtrbrand", "body_type": "hatchback"}).json()["total"] == 1
    assert client.get("/api/cars", params={"brand": "Filtrbrand", "features": "ac,camera"}).json()["total"] == 1
    assert client.get("/api/cars", params={"brand": "Filtrbrand", "max_price": 500000}).json()["items"][0]["model"] == "Spark"
    items = client.get("/api/cars", params={"city": "xorazm", "district": "Xiva shahri", "sort": "price_desc"}).json()["items"]
    assert [c["price_per_day"] for c in items] == [1_000_000, 200_000]
    assert client.get(f"/api/cars/{hidden['id']}").status_code == 404
    assert owner.get(f"/api/cars/{hidden['id']}").status_code == 200


# ---------------- Bron, narx, komissiya ----------------
def test_booking_price_breakdown_and_commission_snapshot():
    admin, _ = make_user("admin")
    owner, _ = make_user()
    renter, _ = make_user()
    car = make_car(owner, price_per_day=350_000, deposit=500_000, delivery_price=50_000)
    q = renter.get(f"/api/cars/{car['id']}/quote", params={"start": d(10), "end": d(12), "delivery": "1"}).json()
    assert (q["rent"], q["delivery"], q["total"], q["commission"], q["owner_payout"], q["deposit"]) == \
           (1_050_000, 50_000, 1_100_000, 110_000, 990_000, 500_000)
    b = book(renter, car["id"], 10, 12, delivery=True).json()
    assert (b["total_price"], b["commission_bps"], b["commission"], b["owner_payout"]) == (1_100_000, 1000, 110_000, 990_000)
    assert b["payment_status"] == "on_site"                                   # to'lov ulanmagan: "to'langan" emas
    # Admin komissiyani o'zgartiradi -> eski bron o'zgarmaydi, yangisi yangi foizda
    assert admin.put("/api/admin/settings", json={"commission_percent": 15}, headers=H).status_code == 200
    renter2, _ = make_user()
    b2 = book(renter2, car["id"], 20, 21).json()
    assert b2["commission_bps"] == 1500 and b2["commission"] == 105_000
    old = [x for x in owner.get("/api/bookings/incoming").json()["items"] if x["id"] == b["id"]][0]
    assert old["commission"] == 110_000
    # E'lon narxi o'zgarsa ham eski bron narxi muzlatilgan
    owner.put(f"/api/cars/{car['id']}", json={**CAR, "price_per_day": 999_000}, headers=H)
    old = [x for x in owner.get("/api/bookings/incoming").json()["items"] if x["id"] == b["id"]][0]
    assert old["total_price"] == 1_100_000
    assert any(a["action"] == "commission_changed" for a in admin.get("/api/admin/audit").json()["items"])
    admin.put("/api/admin/settings", json={"commission_percent": 10}, headers=H)


def test_booking_flow_holds_and_releases_dates():
    owner, _ = make_user()
    r1, _ = make_user()
    r2, _ = make_user()
    car = make_car(owner)
    b1 = book(r1, car["id"], 5, 7).json()
    assert book(r2, car["id"], 6, 9).status_code == 409                       # pending sanalarni band qiladi
    assert r2.get(f"/api/cars/{car['id']}/quote", params={"start": d(6), "end": d(6)}).json()["available"] is False
    assert owner.post(f"/api/bookings/{b1['id']}/approve", headers=H).json()["status"] == "approved"
    assert book(r2, car["id"], 8, 8).status_code == 201                       # qo'shni bo'sh kun
    # Bekor qilingan bron sanalari bo'shaydi
    b3 = book(r2, car["id"], 15, 16).json()
    r2.post(f"/api/bookings/{b3['id']}/cancel", headers=H)
    assert book(r1, car["id"], 15, 16).status_code == 201
    cal = r2.get(f"/api/cars/{car['id']}/calendar").json()
    assert {"start_date": d(5), "end_date": d(7), "status": "approved"} in cal["ranges"]


def test_pending_expires_after_24h():
    owner, _ = make_user()
    renter, ru = make_user()
    car = make_car(owner)
    b = book(renter, car["id"], 5, 6).json()
    with get_db() as db:
        db.execute("UPDATE bookings SET created_at = datetime('now', '-25 hours') WHERE id = ?", (b["id"],))
    assert renter.get("/api/bookings/mine").json()["items"][0]["status"] == "rejected"
    assert book(make_user()[0], car["id"], 5, 6).status_code == 201


def test_parallel_booking_only_one_wins():
    """20 ta foydalanuvchi bir vaqtda bir xil sanani bron qiladi — faqat bittasi o'tadi."""
    owner, _ = make_user()
    car = make_car(owner)
    clients = [make_user()[0] for _ in range(20)]
    results, barrier = [], threading.Barrier(20)

    def go(c):
        barrier.wait()
        results.append(book(c, car["id"], 30, 32).status_code)

    threads = [threading.Thread(target=go, args=(c,)) for c in clients]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(201) == 1 and results.count(409) == 19


def test_booking_validation():
    owner, _ = make_user()
    renter, _ = make_user()
    car = make_car(owner, min_days=2, max_days=5, delivery_price=None)
    assert book(renter, car["id"], -1, 1).status_code == 400
    assert book(renter, car["id"], 5, 3).status_code == 400
    assert book(renter, car["id"], 3, 3).status_code == 400                   # min 2 kun
    assert book(renter, car["id"], 3, 10).status_code == 400                  # max 5 kun
    assert book(renter, car["id"], 3, 4, delivery=True).status_code == 400    # yetkazish yo'q
    assert book(renter, 999999, 1, 2).status_code == 404


def test_pending_limit_per_user():
    owner, _ = make_user()
    renter, _ = make_user()
    cars = [make_car(owner) for _ in range(4)]
    for c in cars[:3]:
        assert book(renter, c["id"], 3, 4).status_code == 201
    assert book(renter, cars[3]["id"], 3, 4).status_code == 429


# ---------------- Ikki tomonlama sharh ----------------
def test_two_sided_reviews():
    owner, _ = make_user()
    renter, ru = make_user()
    car = make_car(owner)
    b = book(renter, car["id"], 1, 2).json()
    owner.post(f"/api/bookings/{b['id']}/approve", headers=H)
    assert renter.post("/api/reviews", headers=H, json={"booking_id": b["id"], "rating": 5}).status_code == 400
    finish(b["id"])
    r = renter.post("/api/reviews", headers=H, json={"booking_id": b["id"], "rating": 4, "comment": "Yaxshi"})
    assert r.status_code == 201 and r.json()["kind"] == "car"
    assert renter.post("/api/reviews", headers=H, json={"booking_id": b["id"], "rating": 5}).status_code == 409
    o = owner.post("/api/reviews", headers=H, json={"booking_id": b["id"], "rating": 5, "comment": "Vaqtida qaytardi"})
    assert o.status_code == 201 and o.json()["kind"] == "renter" and o.json()["target_user_id"] == ru["id"]
    stranger, _ = make_user()
    assert stranger.post("/api/reviews", headers=H, json={"booking_id": b["id"], "rating": 1}).status_code == 404
    assert stranger.post(f"/api/reviews/{r.json()['id']}/reply", headers=H, json={"reply": "x"}).status_code == 403
    assert owner.post(f"/api/reviews/{r.json()['id']}/reply", headers=H, json={"reply": "Rahmat!"}).status_code == 200
    car_now = renter.get(f"/api/cars/{car['id']}").json()
    assert car_now["rating"] == 4.0 and car_now["reviews_count"] == 1
    inc = [x for x in owner.get("/api/bookings/incoming").json()["items"] if x["id"] == b["id"]][0]
    assert inc["renter_rating"] == 5.0


# ---------------- Sevimlilar, narx taxmini, tavsiyalar ----------------
def test_favorites():
    owner, _ = make_user()
    u, _ = make_user()
    car = make_car(owner)
    assert u.put(f"/api/favorites/{car['id']}", headers=H).status_code == 200
    assert u.put(f"/api/favorites/{car['id']}", headers=H).status_code == 200            # idempotent
    assert [c["id"] for c in u.get("/api/favorites").json()["items"]] == [car["id"]]
    assert u.get(f"/api/cars/{car['id']}").json()["is_favorite"] is True
    u.delete(f"/api/favorites/{car['id']}", headers=H)
    assert u.get("/api/favorites").json()["items"] == []


def test_price_suggestion_uses_real_comparables(client):
    owner, _ = make_user()
    for p in (300_000, 320_000, 340_000, 360_000, 380_000):
        make_car(owner, brand="Narxtest", model="X1", city="Qashqadaryo", year=2022, price_per_day=p)
    r = client.get("/api/pricing/suggest", params={"brand": "Narxtest", "model": "X1", "year": 2022, "city": "Qashqadaryo",
                                                    "body_type": "sedan"}).json()
    assert r["n"] >= 5 and r["level"] == "same_model_city" and r["low"] <= r["suggested"] <= r["high"]
    base = 340_000 * {6: 1.10, 7: 1.12, 8: 1.10, 12: 1.05, 1: 1.05, 3: 1.05}.get(date.today().month, 1.0)
    assert abs(r["suggested"] - base) <= 10_000
    newer = client.get("/api/pricing/suggest", params={"brand": "Narxtest", "model": "X1", "year": 2024, "city": "Qashqadaryo",
                                                        "body_type": "sedan"}).json()
    assert newer["suggested"] > r["suggested"]                                # yangi avtomobil qimmatroq
    none = client.get("/api/pricing/suggest", params={"brand": "Yoq", "model": "Yoq", "city": "Mars", "body_type": "pickup"}).json()
    assert none["confidence"] in ("none", "low")


def test_recommendations_exclude_own_and_busy_cars():
    owner, _ = make_user()
    u, _ = make_user()
    own = make_car(u, brand="Mening")
    busy = make_car(owner, brand="Band")
    other_renter, _ = make_user()
    book(other_renter, busy["id"], 40, 42)
    items = u.get("/api/recommendations", params={"limit": 24, "start": d(40), "end": d(41)}).json()["items"]
    ids = [c["id"] for c in items]
    assert own["id"] not in ids and busy["id"] not in ids
    assert all(c.get("reason") for c in items)


# ---------------- Admin ----------------
def test_admin_block_hide_and_audit():
    admin, a = make_user("admin")
    owner, o = make_user()
    car = make_car(owner, brand="Admintest")
    assert admin.patch(f"/api/admin/cars/{car['id']}", json={"is_approved": False}, headers=H).status_code == 200
    assert admin.get("/api/cars", params={"brand": "Admintest"}).json()["total"] == 0
    assert admin.patch(f"/api/admin/users/{o['id']}", json={"is_active": False}, headers=H).status_code == 200
    assert owner.get("/api/auth/me").json()["user"] is None
    assert admin.patch(f"/api/admin/users/{a['id']}", json={"is_active": False}, headers=H).status_code == 400
    actions = [x["action"] for x in admin.get("/api/admin/audit").json()["items"]]
    assert "car_hidden" in actions and "user_blocked" in actions
    stats = admin.get("/api/admin/stats").json()
    assert {"users", "cars", "commission_total", "by_city", "by_body", "user_growth"} <= stats.keys()
    csv = admin.get("/api/admin/finance.csv")
    assert csv.status_code == 200 and "commission_uzs" in csv.text


def _jpeg_with_gps() -> bytes:
    import io

    from PIL import Image
    im = Image.new("RGB", (2400, 1200), (30, 64, 175))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"                        # Make
    exif[0x8825] = {1: "N", 2: (41.0, 18.0, 0.0)}      # GPSInfo: Toshkent koordinatasi
    out = io.BytesIO()
    im.save(out, "JPEG", exif=exif)
    return out.getvalue()


def test_image_reencoded_and_exif_stripped():
    import io

    from PIL import Image
    owner, _ = make_user()
    car = make_car(owner)
    raw = _jpeg_with_gps()
    assert Image.open(io.BytesIO(raw)).getexif()        # asl faylda EXIF/GPS bor
    r = owner.post(f"/api/cars/{car['id']}/images", headers=H, files=[("images", ("phone.jpg", raw, "image/jpeg"))])
    assert r.status_code == 201
    stored = owner.get(r.json()["images"][0]["path"]).content
    im = Image.open(io.BytesIO(stored))
    assert not im.getexif() and max(im.size) <= 1600     # metama'lumot yo'q, o'lcham kichraytirilgan


def test_image_upload_validation():
    import io

    from PIL import Image
    owner, _ = make_user()
    other, _ = make_user()
    car = make_car(owner)
    buf = io.BytesIO(); Image.new("RGB", (40, 30), (200, 10, 10)).save(buf, "PNG")
    png = buf.getvalue()
    r = owner.post(f"/api/cars/{car['id']}/images", headers=H, files=[("images", ("a.png", png, "image/png")),
                                                                       ("images", ("b.png", png, "image/png"))])
    assert r.status_code == 201 and len(r.json()["images"]) == 2
    assert owner.post(f"/api/cars/{car['id']}/images", headers=H,
                      files=[("images", ("x.jpg", b"<?php echo 1; ?>", "image/jpeg"))]).status_code == 400
    fake_png = b"\x89PNG\r\n\x1a\n" + b"0" * 100          # sarlavhasi PNG, ichi buzuq -> qayta kodlashda rad
    assert owner.post(f"/api/cars/{car['id']}/images", headers=H,
                      files=[("images", ("y.png", fake_png, "image/png"))]).status_code == 400
    assert other.post(f"/api/cars/{car['id']}/images", headers=H, files=[("images", ("a.png", png, "image/png"))]).status_code == 403
    second = r.json()["images"][1]["id"]
    imgs = owner.post(f"/api/cars/{car['id']}/images/{second}/cover", headers=H).json()["images"]
    assert imgs[0]["id"] == second


def test_dashboards():
    owner, _ = make_user()
    renter, _ = make_user()
    car = make_car(owner, price_per_day=500_000)
    b = book(renter, car["id"], 1, 2).json()
    owner.post(f"/api/bookings/{b['id']}/approve", headers=H)
    od = owner.get("/api/dashboard/owner").json()
    assert (od["revenue_total"], od["commission_total"], od["payout_total"]) == (1_000_000, 100_000, 900_000)
    assert od["bookings"]["approved"] == 1 and len(od["monthly"]) == 12 and len(od["daily"]) == 30 and od["per_car"][0]["id"] == car["id"]
    rd = renter.get("/api/dashboard/renter").json()
    assert rd["spent_total"] == 1_000_000 and rd["upcoming"]["id"] == b["id"]


def test_unknown_api_and_static(client):
    assert client.get("/api/nope").status_code == 404
    assert client.get("/locales/ru.json").status_code == 200


def test_frontend_translations_complete():
    """Frontend'da ishlatilgan har bir kalit uchala til faylida bor va bo'sh emas."""
    import json
    import re
    static = Path(__file__).resolve().parent.parent / "static"
    langs = {l: json.loads((static / "locales" / f"{l}.json").read_text(encoding="utf-8")) for l in ("uz", "ru", "en")}
    assert set(langs["uz"]) == set(langs["ru"]) == set(langs["en"])
    used = set()
    for f in list(static.rglob("*.js")) + list(static.glob("*.html")):
        text = f.read_text(encoding="utf-8")
        used |= set(re.findall(r'data-i18n(?:-[a-z]+)?="([^"]+)"', text))
        used |= set(re.findall(r'\bt\("([a-z_]+(?:\.[a-z0-9_]+)+)"\s*[,)]', text))
    missing = {k for k in used if k not in langs["uz"]}
    assert not missing, f"Tarjimasi yo'q: {missing}"
    for l, d in langs.items():
        assert all(isinstance(v, str) and v.strip() for v in d.values()), l
    assert "'" not in "".join(v for k, v in langs["uz"].items() if k != "auth.terms").replace("\\'", "")
