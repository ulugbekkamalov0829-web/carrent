"""Ishonch va hisob: bank kartalari, shaxs/haydovchilik hujjatlari, maxfiy fayllar, hisobni butunlay o'chirish, adminlar.

Kartalar: to'liq raqam va CVV HECH QACHON saqlanmaydi (PCI DSS talabi). Saqlanadi: turi, birinchi 6 va oxirgi 4 raqam,
amal qilish muddati va egasining ismi — foydalanuvchi pul yechishda qaysi kartani tanlaganini bilish uchun yetarli.
Haqiqiy pul o'tkazish Click/Payme kabinetida yoki ularning karta tokeni orqali qilinadi.

Hujjatlar: haydovchilik guvohnomasi, pasport/ID karta va selfi. Fayllar ochiq papkada emas (PRIVATE_DIR):
faqat hujjat egasi va admin ko'radi. Raqamning faqat qisqa ko'rinishi saqlanadi (AF ***567).
Admin tekshirib tasdiqlaydi yoki sababini yozib rad etadi. Guvohnoma + pasport/ID tasdiqlansa — "hujjatlari tasdiqlangan".
"""
import json
import re
import secrets
from datetime import date

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse
from starlette.routing import Route

from ..config import settings
from ..db import get_db, one, rows, transaction
from ..i18n import tr
from ..schemas import Base
from ..security import require, revoke_user_sessions
from ..utils import audit, notify, ok, parse_body, path_int, q_str
from .cars import _image_ext, reencode_image

from pydantic import Field

DOC_KINDS = ("license", "id_card", "selfie")
MAX_DOC_FILES = 3


# ---------------- Maxfiy fayllar ----------------
def save_private_image(content: bytes) -> str:
    max_bytes = settings.MAX_IMAGE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(413, tr("Har bir rasm {n} MB dan oshmasligi kerak", n=settings.MAX_IMAGE_MB))
    if not _image_ext(content[:16]):
        raise HTTPException(400, tr("Faqat JPG, PNG yoki WEBP rasm yuklash mumkin"))
    try:
        clean = reencode_image(content)        # EXIF (joylashuv va h.k.) olib tashlanadi
    except ValueError:
        raise HTTPException(400, tr("Faqat JPG, PNG yoki WEBP rasm yuklash mumkin"))
    name = secrets.token_hex(20) + ".jpg"
    (settings.PRIVATE_DIR / name).write_bytes(clean)
    return name


def remove_private(names: list[str]) -> None:
    for n in names:
        p = settings.PRIVATE_DIR / n
        if re.fullmatch(r"[0-9a-f]{40}\.jpg", n) and p.is_file():
            p.unlink(missing_ok=True)


@require()
async def private_file(request: Request):
    """Fayl faqat unga haqli odamga beriladi: hujjat egasi/admin yoki dalolatnoma tegishli bron ishtirokchilari/admin."""
    name = request.path_params["name"]
    if not re.fullmatch(r"[0-9a-f]{40}\.jpg", name):
        raise HTTPException(404, tr("Fayl topilmadi"))
    user = request.state.user
    like = f'%"{name}"%'
    with get_db() as db:
        allowed = False
        doc = one(db.execute("SELECT user_id FROM user_documents WHERE files LIKE ?", (like,)))
        if doc:
            allowed = user["role"] == "admin" or doc["user_id"] == user["id"]
        else:
            h = one(db.execute("""SELECT b.renter_id, c.owner_id FROM handovers h JOIN bookings b ON b.id = h.booking_id
                                  JOIN cars c ON c.id = b.car_id WHERE h.photos LIKE ?""", (like,)))
            if h:
                allowed = user["role"] == "admin" or user["id"] in (h["renter_id"], h["owner_id"])
    path = settings.PRIVATE_DIR / name
    if not allowed or not path.is_file():
        raise HTTPException(404, tr("Fayl topilmadi"))
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


# ---------------- Bank kartalari ----------------
def luhn_ok(num: str) -> bool:
    total, alt = 0, False
    for ch in reversed(num):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def card_brand(num: str) -> str:
    if num.startswith("8600") or num.startswith("5614"):
        return "uzcard"
    if num.startswith("9860"):
        return "humo"
    if num.startswith("4"):
        return "visa"
    if 51 <= int(num[:2]) <= 55 or 2221 <= int(num[:4]) <= 2720:
        return "mastercard"
    return "other"


class CardIn(Base):
    number: str = Field(min_length=12, max_length=23)
    exp: str = Field(min_length=4, max_length=7)          # MM/YY
    holder: str | None = Field(default=None, max_length=60)


@require("user")
async def my_cards(request: Request):
    with get_db() as db:
        items = rows(db.execute("SELECT id, brand, first6, last4, exp_month, exp_year, holder, is_default, created_at FROM user_cards "
                                "WHERE user_id = ? ORDER BY is_default DESC, id DESC", (request.state.user["id"],)))
    return ok({"items": items})


@require("user")
async def add_card(request: Request):
    data = await parse_body(request, CardIn)
    num = re.sub(r"\D", "", data.number)
    if len(num) not in (16, 19) or not luhn_ok(num):
        raise HTTPException(400, tr("Karta raqami noto'g'ri"))
    m = re.fullmatch(r"\s*(\d{1,2})\s*/\s*(\d{2}|\d{4})\s*", data.exp)
    if not m:
        raise HTTPException(400, tr("Amal qilish muddatini OO/YY ko'rinishida yozing"))
    month, year = int(m.group(1)), int(m.group(2))
    year = year + 2000 if year < 100 else year
    t = date.today()
    if not 1 <= month <= 12 or (year, month) < (t.year, t.month) or year > t.year + 15:
        raise HTTPException(400, tr("Kartaning amal qilish muddati tugagan yoki noto'g'ri"))
    uid = request.state.user["id"]
    with get_db() as db:
        if db.execute("SELECT COUNT(*) FROM user_cards WHERE user_id = ?", (uid,)).fetchone()[0] >= 5:
            raise HTTPException(400, tr("Ko'pi bilan 5 ta karta qo'shish mumkin"))
        first = not db.execute("SELECT 1 FROM user_cards WHERE user_id = ?", (uid,)).fetchone()
        try:
            cur = db.execute("INSERT INTO user_cards (user_id, brand, first6, last4, exp_month, exp_year, holder, is_default) "
                             "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                             (uid, card_brand(num), num[:6], num[-4:], month, year, (data.holder or "").upper() or None, int(first)))
        except Exception:
            raise HTTPException(409, tr("Bu karta allaqachon qo'shilgan"))
        audit(db, request, "card_added", "card", cur.lastrowid, last4=num[-4:])
    return await my_cards(request)


@require("user")
async def delete_card(request: Request):
    cid, uid = path_int(request), request.state.user["id"]
    with get_db() as db:
        row = one(db.execute("SELECT is_default FROM user_cards WHERE id = ? AND user_id = ?", (cid, uid)))
        if not row:
            raise HTTPException(404, tr("Karta topilmadi"))
        db.execute("DELETE FROM user_cards WHERE id = ?", (cid,))
        if row["is_default"]:
            db.execute("UPDATE user_cards SET is_default = 1 WHERE id = (SELECT id FROM user_cards WHERE user_id = ? ORDER BY id DESC LIMIT 1)", (uid,))
    return await my_cards(request)


@require("user")
async def default_card(request: Request):
    cid, uid = path_int(request), request.state.user["id"]
    with get_db() as db:
        if not db.execute("SELECT 1 FROM user_cards WHERE id = ? AND user_id = ?", (cid, uid)).fetchone():
            raise HTTPException(404, tr("Karta topilmadi"))
        db.execute("UPDATE user_cards SET is_default = (id = ?) WHERE user_id = ?", (cid, uid))
    return await my_cards(request)


# ---------------- Hujjatlar ----------------
def docs_state(db, uid: int) -> dict:
    """Har bir tur bo'yicha oxirgi hujjat va umumiy holat: verified | pending | rejected | none."""
    out = {}
    for k in DOC_KINDS:
        d = one(db.execute("SELECT id, kind, files, number_mask, categories, expires_on, status, reject_reason, created_at, reviewed_at "
                           "FROM user_documents WHERE user_id = ? AND kind = ? ORDER BY id DESC LIMIT 1", (uid, k)))
        if d:
            d["files"] = json.loads(d["files"])
            if k == "license" and d["status"] == "approved" and d["expires_on"] and d["expires_on"] < date.today().isoformat():
                d["status"], d["expired"] = "rejected", True
        out[k] = d
    need = [out["license"], out["id_card"]]
    if all(d and d["status"] == "approved" for d in need):
        status = "verified"
    elif any(d and d["status"] == "pending" for d in need):
        status = "pending"
    elif any(d and d["status"] == "rejected" for d in need):
        status = "rejected"
    else:
        status = "none"
    return {"status": status, "docs": out}


def docs_verified(db, uid: int) -> bool:
    return docs_state(db, uid)["status"] == "verified"


def _mask(num: str | None) -> str | None:
    if not num:
        return None
    s = re.sub(r"[^A-Za-z0-9]", "", num).upper()
    if len(s) < 5:
        return None
    letters = re.match(r"[A-Z]*", s).group(0)
    return f"{letters} ***{s[-3:]}".strip()


@require("user")
async def my_documents(request: Request):
    with get_db() as db:
        return ok(docs_state(db, request.state.user["id"]))


@require("user")
async def upload_document(request: Request):
    uid = request.state.user["id"]
    async with request.form(max_files=MAX_DOC_FILES, max_fields=10) as form:
        kind = str(form.get("kind") or "")
        if kind not in DOC_KINDS:
            raise HTTPException(400, tr("Hujjat turi noto'g'ri"))
        number = str(form.get("number") or "").strip()[:30]
        categories = re.sub(r"[^A-Z, ]", "", str(form.get("categories") or "").upper())[:20] or None
        expires = str(form.get("expires_on") or "").strip() or None
        if expires:
            try:
                if date.fromisoformat(expires) < date.today():
                    raise HTTPException(400, tr("Hujjatning amal qilish muddati tugagan"))
            except ValueError:
                raise HTTPException(400, tr("Sana noto'g'ri"))
        if kind == "license" and (not number or not expires or not categories):
            raise HTTPException(400, tr("Guvohnoma raqami, toifasi va amal qilish muddatini kiriting"))
        if kind == "id_card" and not number:
            raise HTTPException(400, tr("Pasport yoki ID karta seriya va raqamini kiriting"))
        files = [f for f in form.getlist("files") if hasattr(f, "read")]
        if not files:
            raise HTTPException(400, tr("Rasm tanlanmagan"))
        names = []
        try:
            for f in files[:MAX_DOC_FILES]:
                names.append(save_private_image(await f.read(settings.MAX_IMAGE_MB * 1024 * 1024 + 1)))
        except HTTPException:
            remove_private(names)
            raise
    with get_db() as db, transaction(db):
        old = rows(db.execute("SELECT id, files FROM user_documents WHERE user_id = ? AND kind = ? AND status != 'approved'", (uid, kind)))
        for o in old:
            remove_private(json.loads(o["files"]))
            db.execute("DELETE FROM user_documents WHERE id = ?", (o["id"],))
        db.execute("INSERT INTO user_documents (user_id, kind, files, number_mask, categories, expires_on) VALUES (?, ?, ?, ?, ?, ?)",
                   (uid, kind, json.dumps(names), _mask(number), categories, expires))
        for a in db.execute("SELECT id FROM users WHERE role = 'admin' AND is_active = 1").fetchall():
            notify(db, a[0], "doc_submitted", "/admin.html#documents", mode="admin", actor_id=uid, kind=kind)
        state = docs_state(db, uid)
    return ok(state, 201)


@require("user")
async def delete_document(request: Request):
    did, uid = path_int(request), request.state.user["id"]
    with get_db() as db:
        d = one(db.execute("SELECT files, status FROM user_documents WHERE id = ? AND user_id = ?", (did, uid)))
        if not d:
            raise HTTPException(404, tr("Hujjat topilmadi"))
        remove_private(json.loads(d["files"]))
        db.execute("DELETE FROM user_documents WHERE id = ?", (did,))
        return ok(docs_state(db, uid))


@require("admin")
async def admin_documents(request: Request):
    status = q_str(request, "status") or "pending"
    if status not in ("pending", "approved", "rejected"):
        raise HTTPException(400, tr("Filtr qiymati noto'g'ri"))
    with get_db() as db:
        items = rows(db.execute(
            """SELECT d.*, u.full_name, u.email, u.phone, u.avatar,
                      (SELECT COUNT(*) FROM bookings b WHERE b.renter_id = u.id) AS bookings
               FROM user_documents d JOIN users u ON u.id = d.user_id WHERE d.status = ? ORDER BY d.id DESC LIMIT 200""", (status,)))
        for d in items:
            d["files"] = json.loads(d["files"])
        counts = {s: n for s, n in db.execute("SELECT status, COUNT(*) FROM user_documents GROUP BY status")}
    return ok({"items": items, "counts": counts})


class DocReviewIn(Base):
    approve: bool
    reason: str | None = Field(default=None, max_length=500)


@require("admin")
async def admin_review_document(request: Request):
    did = path_int(request)
    data = await parse_body(request, DocReviewIn)
    if not data.approve and len((data.reason or "").strip()) < 3:
        raise HTTPException(400, tr("Sababini yozing (kamida 3 belgi)"))
    with get_db() as db, transaction(db):
        d = one(db.execute("SELECT * FROM user_documents WHERE id = ?", (did,)))
        if not d:
            raise HTTPException(404, tr("Hujjat topilmadi"))
        db.execute("UPDATE user_documents SET status = ?, reject_reason = ?, reviewed_by = ?, reviewed_at = datetime('now') WHERE id = ?",
                   ("approved" if data.approve else "rejected", None if data.approve else data.reason.strip(), request.state.user["id"], did))
        notify(db, d["user_id"], "doc_approved" if data.approve else "doc_rejected", "/settings.html#documents", mode="any",
               kind=d["kind"], text=(data.reason or "").strip())
        audit(db, request, "doc_approved" if data.approve else "doc_rejected", "user", d["user_id"], kind=d["kind"])
        state = docs_state(db, d["user_id"])
    return ok(state)


# ---------------- Hisobni o'chirish va adminlar ----------------
def has_money_history(db, uid: int) -> bool:
    """Moliyaviy iz bormi: tasdiqlangan/yakunlangan ijara, to'lov yoki o'tkazma. Bor bo'lsa — hisobot uchun anonimlashtiramiz."""
    return bool(db.execute(
        """SELECT 1 FROM bookings b JOIN cars c ON c.id = b.car_id
           WHERE (b.renter_id = :u OR c.owner_id = :u) AND (b.status IN ('approved', 'completed') OR b.payment_status != 'on_site')
           UNION SELECT 1 FROM payments WHERE user_id = :u UNION SELECT 1 FROM payouts WHERE owner_id = :u LIMIT 1""", {"u": uid}).fetchone())


def erase_user(db, uid: int) -> str:
    """Moliyaviy izi bo'lmasa — butunlay o'chiradi (mashinalari, rasmlari, xabarlari bilan); bo'lsa — anonimlashtiradi.
    Ikkala holatda ham email va telefon bo'shaydi: shu email bilan qaytadan ro'yxatdan o'tish mumkin."""
    from ..security import hash_password
    from .cars import _remove_file
    files = [r[0] for r in db.execute("SELECT i.path FROM car_images i JOIN cars c ON c.id = i.car_id WHERE c.owner_id = ?", (uid,))]
    private = [n for (f,) in db.execute("SELECT files FROM user_documents WHERE user_id = ?", (uid,)) for n in json.loads(f)]
    avatar = db.execute("SELECT avatar FROM users WHERE id = ?", (uid,)).fetchone()
    revoke_user_sessions(db, uid)
    if has_money_history(db, uid):
        db.execute("""UPDATE users SET full_name = ?, email = ?, phone = NULL, phone_norm = NULL, region = NULL, district = NULL, avatar = NULL,
                      password_hash = ?, is_active = 0, deleted_at = datetime('now'), marketing_ok = 0, email_verified = 0, phone_verified = 0
                      WHERE id = ?""", ("—", f"deleted-{uid}-{secrets.token_hex(4)}@deleted.local", hash_password(secrets.token_hex(16)), uid))
        db.execute("UPDATE cars SET is_active = 0 WHERE owner_id = ?", (uid,))
        for t in ("favorites", "user_cards", "user_documents", "notifications"):
            db.execute(f"DELETE FROM {t} WHERE user_id = ?", (uid,))
        mode = "anonymized"
    else:
        # Bog'liq yozuvlar (mashinalar, bronlar, xabarlar, sharhlar...) ON DELETE CASCADE bilan o'chadi
        for t in ("reports",):
            db.execute(f"DELETE FROM {t} WHERE reporter_id = ?", (uid,))
        db.execute("DELETE FROM users WHERE id = ?", (uid,))
        for p in files:
            _remove_file(p)
        mode = "deleted"
    remove_private(private)
    if avatar and avatar[0]:
        _remove_file(avatar[0])
    return mode


class ConfirmIn(Base):
    password: str = Field(min_length=1, max_length=200)


@require("admin")
async def admin_set_role(request: Request):
    """Yangi administrator tayinlash yoki admin huquqini olish. O'zini va oxirgi adminni o'zgartirib bo'lmaydi."""
    uid = path_int(request)
    body = await request.json()
    role = body.get("role") if isinstance(body, dict) else None
    if role not in ("admin", "user"):
        raise HTTPException(400, tr("Filtr qiymati noto'g'ri"))
    me = request.state.user["id"]
    with get_db() as db, transaction(db):
        u = one(db.execute("SELECT id, role, email, is_active, deleted_at FROM users WHERE id = ?", (uid,)))
        if not u or u["deleted_at"]:
            raise HTTPException(404, tr("Foydalanuvchi topilmadi"))
        if uid == me:
            raise HTTPException(400, tr("O'z huquqingizni o'zgartira olmaysiz"))
        if role == "admin" and not u["is_active"]:
            raise HTTPException(400, tr("Bloklangan foydalanuvchini admin qilib bo'lmaydi"))
        if role == "user" and db.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1").fetchone()[0] <= 1:
            raise HTTPException(400, tr("Kamida bitta administrator qolishi kerak"))
        db.execute("UPDATE users SET role = ? WHERE id = ?", (role, uid))
        revoke_user_sessions(db, uid)          # yangi huquq bilan qaytadan kirsin
        notify(db, uid, "role_admin" if role == "admin" else "role_user", "/admin.html" if role == "admin" else "/dashboard.html", mode="any")
        audit(db, request, "role_admin" if role == "admin" else "role_user", "user", uid, email=u["email"])
    return ok({"id": uid, "role": role})


@require("admin")
async def admin_erase_user(request: Request):
    uid = path_int(request)
    if uid == request.state.user["id"]:
        raise HTTPException(400, tr("O'zingizni o'chira olmaysiz"))
    with get_db() as db, transaction(db):
        u = one(db.execute("SELECT id, role, email FROM users WHERE id = ?", (uid,)))
        if not u:
            raise HTTPException(404, tr("Foydalanuvchi topilmadi"))
        if u["role"] == "admin":
            raise HTTPException(400, tr("Administrator akkauntiga bu amalni qo'llab bo'lmaydi"))
        active = db.execute("""SELECT COUNT(*) FROM bookings b JOIN cars c ON c.id = b.car_id WHERE b.status IN ('pending', 'approved')
                               AND (b.renter_id = ? OR c.owner_id = ?)""", (uid, uid)).fetchone()[0]
        if active:
            raise HTTPException(409, tr("Foydalanuvchining faol bronlari bor. Avval ularni bekor qiling"))
        mode = erase_user(db, uid)
        audit(db, request, "admin_erase_user", "user", uid, email=u["email"], mode=mode)
    return ok({"id": uid, "mode": mode})


routes = [
    Route("/api/files/{name:str}", private_file, methods=["GET"]),
    Route("/api/me/cards", my_cards, methods=["GET"]),
    Route("/api/me/cards", add_card, methods=["POST"]),
    Route("/api/me/cards/{id:int}", delete_card, methods=["DELETE"]),
    Route("/api/me/cards/{id:int}/default", default_card, methods=["POST"]),
    Route("/api/me/documents", my_documents, methods=["GET"]),
    Route("/api/me/documents", upload_document, methods=["POST"]),
    Route("/api/me/documents/{id:int}", delete_document, methods=["DELETE"]),
    Route("/api/admin/documents", admin_documents, methods=["GET"]),
    Route("/api/admin/documents/{id:int}/review", admin_review_document, methods=["POST"]),
    Route("/api/admin/users/{id:int}/role", admin_set_role, methods=["POST"]),
    Route("/api/admin/users/{id:int}/erase", admin_erase_user, methods=["POST"]),
]
