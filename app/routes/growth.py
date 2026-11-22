"""v10: jarimalar (radar/kamera) va promokodlar.

JARIMALAR: O'zbekistonda radar jarimasi avtomobil egasining nomiga keladi. Ijara vaqtida sodir bo'lgan bo'lsa, owner uni
bron bilan bog'lab yuklaydi (vaqti, summasi, bayonnoma raqami). Tizim vaqt ijara davriga to'g'ri kelishini tekshiradi.
Ijarachi "to'ladim" deydi yoki e'tiroz bildiradi (nizo ochiladi). Ijara tugaganidan keyin 60 kun ichida qo'shish mumkin.
"""
from datetime import date, datetime, timedelta

from pydantic import Field
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.routing import Route

from ..db import get_db, one, rows, transaction
from ..i18n import tr
from ..schemas import Base
from ..security import require
from ..utils import audit, car_title, notify, ok, parse_body, path_int, today

FINE_WINDOW_DAYS = 60


class FineIn(Base):
    happened_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}( \d{2}:\d{2})?$")
    amount: int = Field(ge=1000, le=50_000_000)
    protocol: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=500)


class PromoIn(Base):
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{3,30}$")
    pct: int = Field(default=0, ge=0, le=50)
    amount: int = Field(default=0, ge=0, le=5_000_000)
    max_uses: int | None = Field(default=None, ge=1, le=100_000)
    expires_on: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    note: str | None = Field(default=None, max_length=120)


FINE_SELECT = """SELECT f.*, c.brand, c.model, c.year, b.start_date, b.end_date, ru.full_name AS renter_name, ou.full_name AS owner_name
                 FROM fines f JOIN bookings b ON b.id = f.booking_id JOIN cars c ON c.id = b.car_id
                 JOIN users ru ON ru.id = f.renter_id JOIN users ou ON ou.id = f.owner_id"""


@require()
async def add_fine(request: Request):
    bid = path_int(request)
    data = await parse_body(request, FineIn)
    uid = request.state.user["id"]
    with get_db() as db:
        with transaction(db):
            b = one(db.execute("SELECT b.*, c.owner_id, c.brand, c.model, c.year FROM bookings b JOIN cars c ON c.id = b.car_id "
                               "WHERE b.id = ?", (bid,)))
            if not b:
                raise HTTPException(404, tr("Bron topilmadi"))
            if b["owner_id"] != uid:
                raise HTTPException(403, tr("Bu bron sizning avtomobilingizga tegishli emas"))
            if b["status"] not in ("approved", "completed"):
                raise HTTPException(400, tr("Jarima faqat boshlangan yoki yakunlangan ijaraga qo'shiladi"))
            day = data.happened_at[:10]
            if not b["start_date"] <= day <= b["end_date"]:
                raise HTTPException(400, tr("Jarima vaqti ijara davriga ({start} — {end}) to'g'ri kelmaydi",
                                            start=b["start_date"], end=b["end_date"]))
            if today() > date.fromisoformat(b["end_date"]) + timedelta(days=FINE_WINDOW_DAYS):
                raise HTTPException(400, tr("Ijara tugaganiga {n} kundan oshdi — jarimani qo'shib bo'lmaydi", n=FINE_WINDOW_DAYS))
            if data.protocol and db.execute("SELECT 1 FROM fines WHERE protocol = ? AND status != 'cancelled'",
                                            (data.protocol,)).fetchone():
                raise HTTPException(409, tr("Bu bayonnoma raqami bilan jarima allaqachon qo'shilgan"))
            cur = db.execute("INSERT INTO fines (booking_id, owner_id, renter_id, happened_at, amount, protocol, description) "
                             "VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (bid, uid, b["renter_id"], data.happened_at, data.amount, data.protocol, data.description))
            notify(db, b["renter_id"], "fine_new", "/dashboard.html?mode=renter#fines", actor_id=uid,
                   car=car_title(b), amount=data.amount, at=data.happened_at)
        return ok(one(db.execute(FINE_SELECT + " WHERE f.id = ?", (cur.lastrowid,))), 201)


@require()
async def my_fines(request: Request):
    uid = request.state.user["id"]
    with get_db() as db:
        return ok({"items": rows(db.execute(FINE_SELECT + " WHERE f.renter_id = ? OR f.owner_id = ? ORDER BY f.id DESC", (uid, uid))),
                   "me": uid})


@require()
async def fine_action(request: Request):
    """Ijarachi: paid (to'ladim) | dispute (e'tiroz). Owner: cancel (xato qo'shilgan) | paid (pulni oldim)."""
    fid = path_int(request)
    body = await request.json()
    action = body.get("action")
    uid = request.state.user["id"]
    with get_db() as db:
        with transaction(db):
            f = one(db.execute(FINE_SELECT + " WHERE f.id = ?", (fid,)))
            if not f or uid not in (f["owner_id"], f["renter_id"]):
                raise HTTPException(404, tr("Jarima topilmadi"))
            if f["status"] not in ("open", "disputed"):
                raise HTTPException(400, tr("Bu jarima allaqachon yopilgan"))
            car = car_title(f)
            if action == "paid":
                db.execute("UPDATE fines SET status = 'paid', paid_at = datetime('now') WHERE id = ?", (fid,))
                other = f["owner_id"] if uid == f["renter_id"] else f["renter_id"]
                notify(db, other, "fine_paid", "/dashboard.html#fines", actor_id=uid, car=car, amount=f["amount"])
            elif action == "cancel" and uid == f["owner_id"]:
                db.execute("UPDATE fines SET status = 'cancelled' WHERE id = ?", (fid,))
                notify(db, f["renter_id"], "fine_cancelled", "/dashboard.html?mode=renter#fines", actor_id=uid, car=car)
            elif action == "dispute" and uid == f["renter_id"] and f["status"] == "open":
                db.execute("UPDATE fines SET status = 'disputed' WHERE id = ?", (fid,))
                notify(db, f["owner_id"], "fine_disputed", "/dashboard.html?mode=owner#fines", actor_id=uid, car=car)
            else:
                raise HTTPException(400, tr("Bu amalni bajarib bo'lmaydi"))
        return ok(one(db.execute(FINE_SELECT + " WHERE f.id = ?", (fid,))))


# ---------------- Promokodlar (admin) ----------------
def _promo_rows(db):
    return rows(db.execute(
        """SELECT p.*, (SELECT COUNT(*) FROM bookings b WHERE b.promo_code = p.code COLLATE NOCASE
                        AND b.status NOT IN ('rejected', 'cancelled')) AS used,
                  (SELECT COALESCE(SUM(b.promo_discount), 0) FROM bookings b WHERE b.promo_code = p.code COLLATE NOCASE
                        AND b.status NOT IN ('rejected', 'cancelled')) AS given
           FROM promo_codes p ORDER BY p.id DESC"""))


@require("admin")
async def admin_promos(request: Request):
    with get_db() as db:
        return ok({"items": _promo_rows(db)})


@require("admin")
async def admin_promo_create(request: Request):
    data = await parse_body(request, PromoIn)
    if not data.pct and not data.amount:
        raise HTTPException(400, tr("Foiz yoki summa kiriting"))
    with get_db() as db:
        if db.execute("SELECT 1 FROM promo_codes WHERE code = ? COLLATE NOCASE", (data.code,)).fetchone():
            raise HTTPException(409, tr("Bunday promokod allaqachon bor"))
        db.execute("INSERT INTO promo_codes (code, pct, amount, max_uses, expires_on, note) VALUES (?, ?, ?, ?, ?, ?)",
                   (data.code.upper(), data.pct, data.amount, data.max_uses, data.expires_on, data.note))
        audit(db, request, "promo_created", "promo", None, code=data.code.upper())
        return ok({"items": _promo_rows(db)}, 201)


@require("admin")
async def admin_promo_toggle(request: Request):
    pid = path_int(request)
    with get_db() as db:
        db.execute("UPDATE promo_codes SET is_active = 1 - is_active WHERE id = ?", (pid,))
        audit(db, request, "promo_toggled", "promo", pid)
        return ok({"items": _promo_rows(db)})


routes = [
    Route("/api/bookings/{id:int}/fines", add_fine, methods=["POST"]),
    Route("/api/my/fines", my_fines, methods=["GET"]),
    Route("/api/fines/{id:int}", fine_action, methods=["POST"]),
    Route("/api/admin/promos", admin_promos, methods=["GET"]),
    Route("/api/admin/promos", admin_promo_create, methods=["POST"]),
    Route("/api/admin/promos/{id:int}/toggle", admin_promo_toggle, methods=["POST"]),
]
