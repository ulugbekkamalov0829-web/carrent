"""Kabinet statistikasi (ijarachi, owner) va admin paneli. Barcha raqamlar bazadagi real yozuvlardan hisoblanadi."""
from datetime import date, timedelta

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.routing import Route

from ..db import get_db, get_setting, one, rows
from ..i18n import tr
from ..schemas import AdminCarPatch, AdminUserPatch, SettingsIn
from ..security import require
from ..utils import audit, car_title, notify, ok, parse_body, path_int, q_int, q_str, today
from .bookings import BOOKING_SELECT, maintain

PAID = "('approved', 'completed')"


def _months(n: int = 6) -> list[str]:
    d, out = today().replace(day=1), []
    for _ in range(n):
        out.append(d.strftime("%Y-%m"))
        d = date(d.year - (d.month == 1), (d.month - 2) % 12 + 1, 1)
    return list(reversed(out))


def _monthly(db, where: str, params: list, n: int = 6) -> list[dict]:
    months = _months(n)
    data = {r["m"]: r for r in rows(db.execute(
        f"SELECT substr(b.start_date, 1, 7) AS m, SUM(b.total_price) AS revenue, SUM(b.commission) AS commission, "
        f"SUM(b.owner_payout) AS payout, COUNT(*) AS cnt FROM bookings b JOIN cars c ON c.id = b.car_id "
        f"WHERE {where} AND b.status IN {PAID} AND substr(b.start_date, 1, 7) >= ? GROUP BY m", params + [months[0]]))}
    return [{"month": m, **{k: (data.get(m) or {}).get(k) or 0 for k in ("revenue", "commission", "payout")},
             "count": (data.get(m) or {}).get("cnt") or 0} for m in months]


def _daily(db, where: str, params: list, n: int = 30) -> list[dict]:
    """Oxirgi n kun: har kuni boshlangan (tasdiqlangan/yakunlangan) ijaralar summasi va soni — maydonli grafik uchun."""
    t = today()
    start = t - timedelta(days=n - 1)
    data = {r["d"]: r for r in rows(db.execute(
        f"SELECT b.start_date AS d, SUM(b.total_price) AS revenue, SUM(b.owner_payout) AS payout, COUNT(*) AS cnt FROM bookings b "
        f"JOIN cars c ON c.id = b.car_id WHERE {where} AND b.status IN {PAID} AND b.start_date BETWEEN ? AND ? GROUP BY d",
        params + [start.isoformat(), t.isoformat()]))}
    out = []
    for i in range(n):
        d = (start + timedelta(days=i)).isoformat()
        r = data.get(d) or {}
        out.append({"day": d, "revenue": r.get("revenue") or 0, "payout": r.get("payout") or 0, "count": r.get("cnt") or 0})
    return out


def _status_counts(db, where: str, params: list) -> dict:
    counts = {s: 0 for s in ("pending", "approved", "rejected", "cancelled", "completed")}
    for r in db.execute(f"SELECT b.status, COUNT(*) FROM bookings b JOIN cars c ON c.id = b.car_id WHERE {where} "
                        f"GROUP BY b.status", params):
        counts[r[0]] = r[1]
    return counts


def _occupancy(db, car_ids: list[int], days: int = 30) -> float:
    """Bandlik foizi: oxirgi `days` kunda ijarada bo'lgan kunlar / (avtomobillar × kunlar)."""
    if not car_ids:
        return 0.0
    w_end, w_start = today(), today() - timedelta(days=days - 1)
    marks = ",".join("?" * len(car_ids))
    booked = 0
    for b in db.execute(f"SELECT start_date, end_date FROM bookings WHERE car_id IN ({marks}) AND status IN {PAID} "
                        f"AND start_date <= ? AND end_date >= ?", (*car_ids, w_end.isoformat(), w_start.isoformat())):
        s, e = max(date.fromisoformat(b[0]), w_start), min(date.fromisoformat(b[1]), w_end)
        booked += (e - s).days + 1
    return round(100 * booked / (len(car_ids) * days), 1)


def _period_totals(db, where: str, params: list) -> dict:
    t = today()
    out = {}
    for key, since in (("today", t), ("week", t - timedelta(days=6)), ("month", t.replace(day=1)), ("year", t.replace(month=1, day=1))):
        r = db.execute(f"SELECT COALESCE(SUM(b.total_price), 0), COALESCE(SUM(b.owner_payout), 0) FROM bookings b "
                       f"JOIN cars c ON c.id = b.car_id WHERE {where} AND b.status IN {PAID} AND b.start_date BETWEEN ? AND ?",
                       params + [since.isoformat(), t.isoformat()]).fetchone()
        out[key] = {"revenue": r[0], "payout": r[1]}
    return out


@require()
async def owner_dashboard(request: Request):
    uid = request.state.user["id"]
    with get_db() as db:
        maintain(db)
        car_ids = [r[0] for r in db.execute("SELECT id FROM cars WHERE owner_id = ?", (uid,))]
        cars = db.execute("SELECT COUNT(*), COALESCE(SUM(is_active AND is_approved), 0), COALESCE(SUM(views), 0) FROM cars "
                          "WHERE owner_id = ?", (uid,)).fetchone()
        money = db.execute(f"SELECT COALESCE(SUM(b.total_price), 0), COALESCE(SUM(b.commission), 0), COALESCE(SUM(b.owner_payout), 0) "
                           f"FROM bookings b JOIN cars c ON c.id = b.car_id WHERE c.owner_id = ? AND b.status IN {PAID}", (uid,)).fetchone()
        rating = one(db.execute("SELECT ROUND(AVG(r.rating), 2) AS avg, COUNT(*) AS cnt FROM reviews r JOIN cars c ON c.id = r.car_id "
                                "WHERE c.owner_id = ? AND r.kind = 'car'", (uid,)))
        statuses = _status_counts(db, "c.owner_id = ?", [uid])
        all_bookings = sum(statuses.values())
        per_car = rows(db.execute(
            f"""SELECT c.id, c.brand, c.model, c.year, c.views, COUNT(b.id) AS bookings,
                       COALESCE(SUM(b.total_price), 0) AS revenue, COALESCE(SUM(b.owner_payout), 0) AS payout
                FROM cars c LEFT JOIN bookings b ON b.car_id = c.id AND b.status IN {PAID}
                WHERE c.owner_id = ? GROUP BY c.id ORDER BY revenue DESC""", (uid,)))
        for c in per_car:
            c["occupancy"] = _occupancy(db, [c["id"]])
        result = {
            "cars_total": cars[0], "cars_active": cars[1], "views_total": cars[2],
            "revenue_total": money[0], "commission_total": money[1], "payout_total": money[2],
            "rating_avg": rating["avg"], "reviews_count": rating["cnt"], "bookings": statuses,
            "conversion": round(100 * all_bookings / cars[2], 1) if cars[2] else 0.0,
            "occupancy": _occupancy(db, car_ids), "periods": _period_totals(db, "c.owner_id = ?", [uid]),
            "monthly": _monthly(db, "c.owner_id = ?", [uid], 12), "daily": _daily(db, "c.owner_id = ?", [uid]), "per_car": per_car,
            "commission_bps": int(get_setting(db, "commission_bps", "1000")),
        }
    return ok(result)


@require()
async def renter_dashboard(request: Request):
    uid = request.state.user["id"]
    with get_db() as db:
        maintain(db)
        spent = db.execute(f"SELECT COALESCE(SUM(total_price), 0), COALESCE(SUM(days), 0) FROM bookings "
                           f"WHERE renter_id = ? AND status IN {PAID}", (uid,)).fetchone()
        upcoming = one(db.execute(
            "SELECT b.id, b.start_date, b.end_date, c.brand, c.model, c.year FROM bookings b JOIN cars c ON c.id = b.car_id "
            "WHERE b.renter_id = ? AND b.status = 'approved' AND b.end_date >= ? ORDER BY b.start_date LIMIT 1",
            (uid, today().isoformat())))
        if upcoming:
            upcoming["title"] = car_title(upcoming)
        to_review = db.execute("SELECT COUNT(*) FROM bookings b WHERE b.renter_id = ? AND b.status = 'completed' AND NOT EXISTS "
                               "(SELECT 1 FROM reviews r WHERE r.booking_id = b.id AND r.kind = 'car')", (uid,)).fetchone()[0]
        favs = db.execute("SELECT COUNT(*) FROM favorites WHERE user_id = ?", (uid,)).fetchone()[0]
        my_rating = one(db.execute("SELECT ROUND(AVG(rating), 1) AS avg, COUNT(*) AS cnt FROM reviews "
                                   "WHERE target_user_id = ? AND kind = 'renter'", (uid,)))
        result = {"spent_total": spent[0], "days_total": spent[1], "upcoming": upcoming, "to_review": to_review,
                  "favorites": favs, "my_rating": my_rating, "bookings": _status_counts(db, "b.renter_id = ?", [uid])}
    return ok(result)


# ---------------- Admin ----------------
@require("admin")
async def admin_stats(request: Request):
    with get_db() as db:
        maintain(db)
        users_total = db.execute("SELECT COUNT(*) FROM users WHERE role = 'user'").fetchone()[0]
        blocked = db.execute("SELECT COUNT(*) FROM users WHERE is_active = 0").fetchone()[0]
        owners = db.execute("SELECT COUNT(DISTINCT owner_id) FROM cars").fetchone()[0]
        renters = db.execute("SELECT COUNT(DISTINCT renter_id) FROM bookings").fetchone()[0]
        active_users = db.execute(
            "SELECT COUNT(*) FROM users u WHERE EXISTS (SELECT 1 FROM bookings b WHERE b.renter_id = u.id AND b.created_at >= datetime('now', '-30 days')) "
            "OR EXISTS (SELECT 1 FROM cars c WHERE c.owner_id = u.id AND c.updated_at >= datetime('now', '-30 days')) "
            "OR EXISTS (SELECT 1 FROM messages m WHERE m.sender_id = u.id AND m.created_at >= datetime('now', '-30 days'))").fetchone()[0]
        new_week = db.execute("SELECT COUNT(*) FROM users WHERE created_at >= datetime('now', '-7 days')").fetchone()[0]
        cars = db.execute("SELECT COUNT(*), COALESCE(SUM(is_active AND is_approved), 0), COALESCE(SUM(is_approved = 0), 0) FROM cars").fetchone()
        money = db.execute(f"SELECT COALESCE(SUM(total_price), 0), COALESCE(SUM(commission), 0) FROM bookings WHERE status IN {PAID}").fetchone()
        reviews = one(db.execute("SELECT COUNT(*) AS cnt, ROUND(AVG(rating), 2) AS avg FROM reviews WHERE kind = 'car'"))
        by_city = rows(db.execute(f"SELECT c.city, COUNT(*) AS bookings, COALESCE(SUM(b.commission), 0) AS commission "
                                  f"FROM bookings b JOIN cars c ON c.id = b.car_id GROUP BY c.city ORDER BY bookings DESC LIMIT 8"))
        by_body = rows(db.execute("SELECT c.body_type, COUNT(*) AS bookings FROM bookings b JOIN cars c ON c.id = b.car_id "
                                  "GROUP BY c.body_type ORDER BY bookings DESC"))
        months = _months(12)
        growth = {r[0]: r[1] for r in db.execute("SELECT substr(created_at, 1, 7), COUNT(*) FROM users WHERE substr(created_at, 1, 7) >= ? "
                                                  "GROUP BY 1", (months[0],))}
        result = {
            "users": {"total": users_total, "active_30d": active_users, "owners": owners, "renters": renters,
                      "blocked": blocked, "new_week": new_week},
            "cars": {"total": cars[0], "active": cars[1], "hidden": cars[2]},
            "revenue_total": money[0], "commission_total": money[1], "reviews": reviews,
            "bookings": _status_counts(db, "1 = 1", []), "monthly": _monthly(db, "1 = 1", [], 12),
            "by_city": by_city, "by_body": by_body,
            "user_growth": [{"month": m, "count": growth.get(m, 0)} for m in months],
            "commission_bps": int(get_setting(db, "commission_bps", "1000")),
            "reports_new": db.execute("SELECT COUNT(*) FROM reports WHERE status = 'new'").fetchone()[0],
            "paid_online": db.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'paid'").fetchone()[0],
            "refunds_pending": db.execute("SELECT COUNT(*) FROM payments WHERE status = 'refund_pending'").fetchone()[0],
            "daily": _daily(db, "1 = 1", []),
            # Admin tasdig'ini kutayotganlar: imzolangan shartnomalar va tekshirilmagan hujjatlar
            "queue": rows(db.execute(
                """SELECT 'contract' AS kind, k.id, k.booking_id, k.number AS title, c.brand, c.model, c.year, c.id AS car_id,
                          (SELECT path FROM car_images i WHERE i.car_id = c.id ORDER BY position, id LIMIT 1) AS cover,
                          ru.full_name AS who, k.created_at AS at, NULL AS user_id, NULL AS avatar
                   FROM contracts k JOIN bookings b ON b.id = k.booking_id JOIN cars c ON c.id = b.car_id JOIN users ru ON ru.id = b.renter_id
                   WHERE k.status = 'signed'
                   UNION ALL
                   SELECT 'doc' AS kind, d.id, NULL, d.kind, NULL, NULL, NULL, NULL, NULL, u.full_name, d.created_at, u.id, u.avatar
                   FROM user_documents d JOIN users u ON u.id = d.user_id WHERE d.status = 'pending'
                   ORDER BY at DESC LIMIT 6""")),
            "latest_users": rows(db.execute(
                """SELECT u.id, u.full_name, u.email, u.phone, u.avatar, u.is_active, u.created_at,
                          (SELECT COUNT(*) FROM bookings b WHERE b.renter_id = u.id) AS bookings
                   FROM users u WHERE u.role = 'user' ORDER BY u.id DESC LIMIT 5""")),
        }
    return ok(result)


@require("admin")
async def admin_users(request: Request):
    sql, params = ("SELECT u.id, u.full_name, u.email, u.phone, u.role, u.is_active, u.created_at, "
                   "(SELECT COUNT(*) FROM cars c WHERE c.owner_id = u.id) AS cars, "
                   "(SELECT COUNT(*) FROM bookings b WHERE b.renter_id = u.id) AS bookings FROM users u WHERE 1 = 1"), []
    if q := q_str(request, "q"):
        sql += " AND (u.full_name LIKE ? OR u.email LIKE ? OR u.phone LIKE ?)"; params += [f"%{q}%"] * 3
    kind = q_str(request, "kind") or ""
    if kind in USER_KINDS:
        sql += " AND " + USER_KINDS[kind]
    with get_db() as db:
        items = rows(db.execute(sql + " ORDER BY u.id DESC LIMIT 300", params))
        counts = {"all": db.execute("SELECT COUNT(*) FROM users u WHERE u.role = 'user'").fetchone()[0]}
        for k, cond in USER_KINDS.items():
            counts[k] = db.execute(f"SELECT COUNT(*) FROM users u WHERE {cond}").fetchone()[0]
    return ok({"items": items, "counts": counts})


ACTIVE_30 = ("(EXISTS (SELECT 1 FROM bookings b WHERE b.renter_id = u.id AND b.created_at >= datetime('now', '-30 days')) "
             "OR EXISTS (SELECT 1 FROM cars c WHERE c.owner_id = u.id AND c.updated_at >= datetime('now', '-30 days')) "
             "OR EXISTS (SELECT 1 FROM messages m WHERE m.sender_id = u.id AND m.created_at >= datetime('now', '-30 days')))")
USER_KINDS = {
    "renters": "u.role = 'user' AND EXISTS (SELECT 1 FROM bookings b WHERE b.renter_id = u.id)",
    "owners": "EXISTS (SELECT 1 FROM cars c WHERE c.owner_id = u.id)",
    "active": "u.role = 'user' AND " + ACTIVE_30,
    "new": "u.role = 'user' AND u.created_at >= datetime('now', '-7 days')",
    "blocked": "u.is_active = 0",
    "admins": "u.role = 'admin'",
}


@require("admin")
async def admin_patch_user(request: Request):
    uid = path_int(request)
    data = await parse_body(request, AdminUserPatch)
    if uid == request.state.user["id"]:
        raise HTTPException(400, tr("O'zingizni bloklay olmaysiz"))
    with get_db() as db:
        target = one(db.execute("SELECT id, role, email FROM users WHERE id = ?", (uid,)))
        if not target:
            raise HTTPException(404, tr("Foydalanuvchi topilmadi"))
        if target["role"] == "admin":
            raise HTTPException(400, tr("Boshqa administratorni bloklab bo'lmaydi"))
        db.execute("UPDATE users SET is_active = ? WHERE id = ?", (int(data.is_active), uid))
        if not data.is_active:
            from ..security import revoke_user_sessions
            revoke_user_sessions(db, uid)
        audit(db, request, "user_unblocked" if data.is_active else "user_blocked", "user", uid, email=target["email"])
    return ok({"id": uid, "is_active": data.is_active})


@require("admin")
async def admin_cars(request: Request):
    sql, params = ("SELECT c.id, c.brand, c.model, c.year, c.city, c.district, c.price_per_day, c.is_active, c.is_approved, c.created_at, "
                   "c.plate, c.tech_passport, c.ownership_status, u.identity_status, "
                   "u.full_name AS owner_name, u.id AS owner_id FROM cars c JOIN users u ON u.id = c.owner_id WHERE 1 = 1"), []
    if q := q_str(request, "q"):
        sql += " AND (c.brand || ' ' || c.model LIKE ? OR u.full_name LIKE ?)"; params += [f"%{q}%"] * 2
    with get_db() as db:
        items = rows(db.execute(sql + " ORDER BY c.id DESC LIMIT 300", params))
    return ok({"items": items})


@require("admin")
async def admin_patch_car(request: Request):
    cid = path_int(request)
    data = await parse_body(request, AdminCarPatch)
    with get_db() as db:
        car = one(db.execute("SELECT id, owner_id, brand, model, year FROM cars WHERE id = ?", (cid,)))
        if not car:
            raise HTTPException(404, tr("E'lon topilmadi"))
        if data.ownership_status is not None:
            db.execute("UPDATE cars SET ownership_status = ? WHERE id = ?", (data.ownership_status, cid))
            audit(db, request, "car_ownership_" + data.ownership_status, "car", cid, title=car_title(car))
        if data.is_approved is not None:
            db.execute("UPDATE cars SET is_approved = ? WHERE id = ?", (int(data.is_approved), cid))
            notify(db, car["owner_id"], "car_approved" if data.is_approved else "car_hidden", "/dashboard.html?mode=owner#cars",
                   car=car_title(car))
            audit(db, request, "car_approved" if data.is_approved else "car_hidden", "car", cid, title=car_title(car))
    return ok({"id": cid, "is_approved": data.is_approved, "ownership_status": data.ownership_status})


@require("admin")
async def admin_bookings(request: Request):
    sql, params = BOOKING_SELECT + " WHERE 1 = 1", []
    if status := q_str(request, "status"):
        sql += " AND b.status = ?"; params.append(status)
    with get_db() as db:
        items = rows(db.execute(sql + " ORDER BY b.id DESC LIMIT 300", params))
    return ok({"items": items})


@require("admin")
async def admin_reviews(request: Request):
    with get_db() as db:
        items = rows(db.execute(
            "SELECT r.id, r.kind, r.rating, r.comment, r.created_at, r.author_id, r.target_user_id, c.brand, c.model, c.id AS car_id, "
            "a.full_name AS author, t.full_name AS target FROM reviews r JOIN cars c ON c.id = r.car_id "
            "JOIN users a ON a.id = r.author_id JOIN users t ON t.id = r.target_user_id ORDER BY r.id DESC LIMIT 300"))
    return ok({"items": items})


@require("admin")
async def admin_delete_review(request: Request):
    rid = path_int(request)
    with get_db() as db:
        cur = db.execute("DELETE FROM reviews WHERE id = ?", (rid,))
        if not cur.rowcount:
            raise HTTPException(404, tr("Sharh topilmadi"))
        audit(db, request, "review_deleted", "review", rid)
    return ok()


@require("admin")
async def admin_settings(request: Request):
    with get_db() as db:
        return ok({"commission_percent": int(get_setting(db, "commission_bps", "1000")) / 100})


@require("admin")
async def admin_update_settings(request: Request):
    data = await parse_body(request, SettingsIn)
    bps = round(data.commission_percent * 100)
    if not 0 <= bps <= 3000:
        raise HTTPException(400, tr("Komissiya 0% dan 30% gacha bo'lishi kerak"))
    with get_db() as db:
        old = get_setting(db, "commission_bps", "1000")
        db.execute("UPDATE settings SET value = ?, updated_at = datetime('now') WHERE key = 'commission_bps'", (str(bps),))
        audit(db, request, "commission_changed", "settings", None, old_bps=int(old), new_bps=bps)
    return ok({"commission_percent": bps / 100})


def report_label(db, r: dict) -> dict:
    """Shikoyat obyekti haqida qisqa ma'lumot va aynan kim ustidan ekani (admin o'sha odam sahifasiga o'tadi)."""
    from .admin_users import report_target_user
    if r["target_type"] == "car":
        c = one(db.execute(f"SELECT brand, model, year, is_approved, {COVER_SQL} AS cover FROM cars c WHERE id = ?", (r["target_id"],)))
        r["target_label"] = f"{c['brand']} {c['model']} {c['year']}" if c else "—"
        r["cover"] = c["cover"] if c else None
        r["link"] = f"/car.html?id={r['target_id']}"
    elif r["target_type"] == "review":
        c = one(db.execute("SELECT comment, rating, car_id FROM reviews WHERE id = ?", (r["target_id"],)))
        r["target_label"] = (f"★{c['rating']} “{(c['comment'] or '')[:80]}”") if c else "—"
        r["link"] = f"/car.html?id={c['car_id']}#reviews" if c else None
    elif r["target_type"] == "user":
        c = one(db.execute("SELECT full_name, email FROM users WHERE id = ?", (r["target_id"],)))
        r["target_label"] = f"{c['full_name']} ({c['email']})" if c else "—"
        r["link"] = None
    else:
        c = one(db.execute("SELECT m.body, u.full_name FROM messages m JOIN users u ON u.id = m.sender_id WHERE m.id = ?",
                           (r["target_id"],)))
        r["target_label"] = f"{c['full_name']}: “{c['body'][:80]}”" if c else "—"
        r["link"] = None
    tu = report_target_user(db, r["target_type"], r["target_id"])
    r["target_user_id"] = tu
    if tu:
        x = one(db.execute("SELECT full_name, avatar, is_active, (SELECT COUNT(*) FROM admin_notes n WHERE n.user_id = users.id AND n.kind = 'warning') AS warnings "
                           "FROM users WHERE id = ?", (tu,)))
        if x:
            r.update(target_user_name=x["full_name"], target_user_avatar=x["avatar"], target_user_active=x["is_active"],
                     target_user_warnings=x["warnings"])
    return r


COVER_SQL = "(SELECT path FROM car_images i WHERE i.car_id = c.id ORDER BY position, id LIMIT 1)"


@require("admin")
async def admin_reports(request: Request):
    status = q_str(request, "status") or "new"
    with get_db() as db:
        items = rows(db.execute(
            "SELECT r.*, u.full_name AS reporter_name FROM reports r JOIN users u ON u.id = r.reporter_id "
            "WHERE r.status = ? ORDER BY r.id DESC LIMIT 200", (status,)))
        for r in items:
            report_label(db, r)
    return ok({"items": items})


@require("admin")
async def admin_patch_report(request: Request):
    from ..schemas import ReportPatch
    from ..security import revoke_user_sessions
    rid = path_int(request)
    data = await parse_body(request, ReportPatch)
    with get_db() as db:
        r = one(db.execute("SELECT * FROM reports WHERE id = ?", (rid,)))
        if not r:
            raise HTTPException(404, tr("Shikoyat obyekti topilmadi"))
        if data.action == "hide_car" and r["target_type"] == "car":
            db.execute("UPDATE cars SET is_approved = 0 WHERE id = ?", (r["target_id"],))
        elif data.action == "delete_review" and r["target_type"] == "review":
            db.execute("DELETE FROM reviews WHERE id = ?", (r["target_id"],))
        elif data.action in ("block_user", "warn_user"):
            from .admin_users import report_target_user
            uid = report_target_user(db, r["target_type"], r["target_id"])
            if uid and db.execute("SELECT role FROM users WHERE id = ?", (uid,)).fetchone()[0] != "admin":
                reason = r["reason"]
                if data.action == "block_user":
                    db.execute("UPDATE users SET is_active = 0 WHERE id = ?", (uid,))
                    revoke_user_sessions(db, uid)
                    kind = "block"
                else:
                    notify(db, uid, "admin_warning", "/settings.html", mode="any", text=data.note or "", reason=r["reason"])
                    kind = "warning"
                db.execute("INSERT INTO admin_notes (user_id, author_id, kind, body) VALUES (?, ?, ?, ?)",
                           (uid, request.state.user["id"], kind, f"#{rid} [{reason}] {data.note or r['comment'] or ''}".strip()))
        db.execute("UPDATE reports SET status = ?, resolved_by = ?, resolved_at = datetime('now') WHERE id = ?",
                   (data.status, request.state.user["id"], rid))
        audit(db, request, f"report_{data.status}", "report", rid, act=data.action)
    return ok()


@require("admin")
async def admin_audit(request: Request):
    with get_db() as db:
        items = rows(db.execute(
            "SELECT a.*, u.full_name AS actor_name FROM audit_logs a LEFT JOIN users u ON u.id = a.actor_id "
            "ORDER BY a.id DESC LIMIT ?", (q_int(request, "limit", 100, lo=1, hi=500),)))
    return ok({"items": items})


@require("admin")
async def admin_finance_csv(request: Request):
    """Moliya hisoboti: har bir bron bo'yicha tushum, komissiya va owner ulushi (Excel ochadi)."""
    from starlette.responses import Response
    with get_db() as db:
        data = rows(db.execute(BOOKING_SELECT + f" WHERE b.status IN {PAID} ORDER BY b.start_date DESC"))
    lines = ["id;start;end;car;renter;owner;total_uzs;commission_bps;commission_uzs;owner_payout_uzs;status"]
    for b in data:
        name = f"{b['brand']} {b['model']} {b['year']}".replace(";", ",")
        lines.append(f"{b['id']};{b['start_date']};{b['end_date']};{name};{b['renter_name'].replace(';', ',')};"
                     f"{b['owner_name'].replace(';', ',')};{b['total_price']};{b['commission_bps']};{b['commission']};"
                     f"{b['owner_payout']};{b['status']}")
    return Response("﻿" + "\r\n".join(lines), media_type="text/csv; charset=utf-8",
                    headers={"content-disposition": f"attachment; filename=carrent-finance-{today().isoformat()}.csv"})


routes = [
    Route("/api/dashboard/owner", owner_dashboard, methods=["GET"]),
    Route("/api/dashboard/renter", renter_dashboard, methods=["GET"]),
    Route("/api/admin/stats", admin_stats, methods=["GET"]),
    Route("/api/admin/users", admin_users, methods=["GET"]),
    Route("/api/admin/users/{id:int}", admin_patch_user, methods=["PATCH"]),
    Route("/api/admin/cars", admin_cars, methods=["GET"]),
    Route("/api/admin/cars/{id:int}", admin_patch_car, methods=["PATCH"]),
    Route("/api/admin/bookings", admin_bookings, methods=["GET"]),
    Route("/api/admin/reviews", admin_reviews, methods=["GET"]),
    Route("/api/admin/reviews/{id:int}", admin_delete_review, methods=["DELETE"]),
    Route("/api/admin/settings", admin_settings, methods=["GET"]),
    Route("/api/admin/settings", admin_update_settings, methods=["PUT"]),
    Route("/api/admin/audit", admin_audit, methods=["GET"]),
    Route("/api/admin/reports", admin_reports, methods=["GET"]),
    Route("/api/admin/reports/{id:int}", admin_patch_report, methods=["PATCH"]),
    Route("/api/admin/finance.csv", admin_finance_csv, methods=["GET"]),
]
