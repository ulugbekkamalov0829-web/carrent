"""Ma'lumotlar bazasi: SQLite (WAL rejimi, tashqi kalitlar yoqilgan).

Pul summalari INTEGER (butun so'm), foizlar basis points (10% = 1000) — floating-point ishlatilmaydi.
"""
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    phone         TEXT,
    region        TEXT,
    district      TEXT,
    password_hash TEXT    NOT NULL,
    -- Faqat ikki rol: 'user' (ham ijarachi, ham owner bo'la oladi) va 'admin'
    role          TEXT    NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    -- Rejim faqat interfeysni belgilaydi; ruxsatlar egalik bo'yicha tekshiriladi
    active_mode   TEXT    NOT NULL DEFAULT 'renter' CHECK (active_mode IN ('renter', 'owner')),
    lang          TEXT    NOT NULL DEFAULT 'uz' CHECK (lang IN ('uz', 'ru', 'en')),
    marketing_ok  INTEGER NOT NULL DEFAULT 0,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    phone_norm    TEXT,                          -- +998XXXXXXXXX ko'rinishida: telefon bilan kirish uchun
    email_verified INTEGER NOT NULL DEFAULT 0,
    phone_verified INTEGER NOT NULL DEFAULT 0,
    avatar        TEXT,
    show_phone    INTEGER NOT NULL DEFAULT 1,    -- telefon tizimga kirganlarga ko'rinsinmi
    notify_prefs  TEXT    NOT NULL DEFAULT '{}', -- {"email_booking": true, ...}
    deleted_at    TEXT
);

CREATE TABLE IF NOT EXISTS cars (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    brand            TEXT    NOT NULL,
    model            TEXT    NOT NULL,
    year             INTEGER NOT NULL,
    color            TEXT,
    body_type        TEXT    NOT NULL CHECK (body_type IN ('sedan', 'hatchback', 'crossover', 'suv', 'minivan', 'pickup', 'coupe')),
    seats            INTEGER NOT NULL CHECK (seats BETWEEN 1 AND 20),
    transmission     TEXT    NOT NULL CHECK (transmission IN ('automatic', 'manual')),
    fuel             TEXT    NOT NULL CHECK (fuel IN ('petrol', 'gas', 'diesel', 'hybrid', 'electric')),
    engine_l         REAL,
    mileage_km       INTEGER,
    drive            TEXT    CHECK (drive IN ('fwd', 'rwd', 'awd')),
    features         TEXT    NOT NULL DEFAULT '[]',   -- JSON ro'yxat: ac, bluetooth, usb, camera, ...
    city             TEXT    NOT NULL,
    district         TEXT,
    description      TEXT,
    price_per_day    INTEGER NOT NULL CHECK (price_per_day > 0),
    deposit          INTEGER NOT NULL DEFAULT 0 CHECK (deposit >= 0),
    min_days         INTEGER NOT NULL DEFAULT 1 CHECK (min_days >= 1),
    max_days         INTEGER NOT NULL DEFAULT 30 CHECK (max_days >= min_days),
    km_limit         INTEGER,                          -- kunlik masofa limiti, NULL = cheksiz
    delivery_price   INTEGER,                          -- NULL = yetkazib berish yo'q
    is_active        INTEGER NOT NULL DEFAULT 1,       -- owner vaqtincha yashirishi mumkin
    is_approved      INTEGER NOT NULL DEFAULT 1,       -- admin moderatsiyasi
    views            INTEGER NOT NULL DEFAULT 0,
    is_demo          INTEGER NOT NULL DEFAULT 0,       -- demo ma'lumot, interfeysda aniq belgilanadi
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_cars_owner ON cars(owner_id);
CREATE INDEX IF NOT EXISTS ix_cars_search ON cars(is_active, is_approved, city, price_per_day);
CREATE INDEX IF NOT EXISTS ix_cars_model ON cars(brand, model, year);

CREATE TABLE IF NOT EXISTS car_images (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id    INTEGER NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
    path      TEXT    NOT NULL,
    position  INTEGER NOT NULL DEFAULT 0,
    label     TEXT    NOT NULL DEFAULT 'other'   -- front, back, side, interior, dashboard, trunk, other
);
CREATE INDEX IF NOT EXISTS ix_images_car ON car_images(car_id);

CREATE TABLE IF NOT EXISTS bookings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id          INTEGER NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
    renter_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    start_date      TEXT    NOT NULL,             -- YYYY-MM-DD (kiritilgan)
    end_date        TEXT    NOT NULL,             -- YYYY-MM-DD (kiritilgan)
    days            INTEGER NOT NULL,
    -- Narx bron paytida muzlatiladi: keyin e'lon narxi yoki komissiya o'zgarsa ham bu qiymatlar o'zgarmaydi
    price_per_day   INTEGER NOT NULL,
    delivery        INTEGER NOT NULL DEFAULT 0,
    total_price     INTEGER NOT NULL,             -- ijarachi to'laydigan summa (depozitsiz)
    commission_bps  INTEGER NOT NULL,             -- bron paytidagi komissiya foizi
    commission      INTEGER NOT NULL,             -- platforma ulushi
    owner_payout    INTEGER NOT NULL,             -- owner'ga tegishli summa
    deposit         INTEGER NOT NULL DEFAULT 0,   -- qaytariladigan, daromad emas
    payment_status  TEXT    NOT NULL DEFAULT 'on_site'
                    CHECK (payment_status IN ('on_site', 'paid', 'refunded', 'refund_pending')),
    status          TEXT    NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled', 'completed')),
    note            TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    CHECK (end_date >= start_date),
    CHECK (commission + owner_payout = total_price)
);
CREATE INDEX IF NOT EXISTS ix_bookings_car ON bookings(car_id, status, start_date, end_date);
CREATE INDEX IF NOT EXISTS ix_bookings_renter ON bookings(renter_id);

-- Ikki tomonlama sharh: ijarachi avtomobilni (kind='car'), owner ijarachini (kind='renter') baholaydi
CREATE TABLE IF NOT EXISTS reviews (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id     INTEGER NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    car_id         INTEGER NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
    author_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind           TEXT    NOT NULL CHECK (kind IN ('car', 'renter')),
    rating         INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment        TEXT,
    reply          TEXT,                         -- owner javobi (faqat kind='car')
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (booking_id, kind)
);
CREATE INDEX IF NOT EXISTS ix_reviews_car ON reviews(car_id, kind);
CREATE INDEX IF NOT EXISTS ix_reviews_target ON reviews(target_user_id, kind);

CREATE TABLE IF NOT EXISTS favorites (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    car_id     INTEGER NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, car_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    receiver_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    car_id      INTEGER REFERENCES cars(id) ON DELETE SET NULL,
    body        TEXT    NOT NULL,
    is_read     INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_messages_pair ON messages(sender_id, receiver_id);
CREATE INDEX IF NOT EXISTS ix_messages_receiver ON messages(receiver_id, is_read);

-- Bildirishnomalar matni kod (type) + parametrlar bilan saqlanadi: frontend uni foydalanuvchi tiliga o'giradi
CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type       TEXT    NOT NULL,
    params     TEXT    NOT NULL DEFAULT '{}',
    link       TEXT,
    is_read    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_notifications_user ON notifications(user_id, is_read);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT OR IGNORE INTO settings (key, value) VALUES ('commission_bps', '1000');

-- Owner avtomobilni ijaraga bermaydigan kunlar (ta'mir, shaxsiy foydalanish)
CREATE TABLE IF NOT EXISTS car_blocks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id     INTEGER NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
    start_date TEXT    NOT NULL,
    end_date   TEXT    NOT NULL,
    note       TEXT,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    CHECK (end_date >= start_date)
);
CREATE INDEX IF NOT EXISTS ix_blocks_car ON car_blocks(car_id, start_date, end_date);

-- Kirish sessiyalari: har bir qurilma alohida, istalgan payt bekor qilinadi
CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT    PRIMARY KEY,              -- tokendagi jti'ning SHA-256 xeshi
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ip         TEXT,
    user_agent TEXT,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    last_seen  TEXT    NOT NULL DEFAULT (datetime('now')),
    revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_sessions_user ON sessions(user_id, revoked_at);

-- Bir martalik kodlar: parolni tiklash, email/telefonni tasdiqlash, emailni almashtirish (kod ochiq saqlanmaydi)
CREATE TABLE IF NOT EXISTS verification_codes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose    TEXT    NOT NULL CHECK (purpose IN ('reset', 'verify_email', 'verify_phone', 'change_email')),
    channel    TEXT    NOT NULL CHECK (channel IN ('email', 'sms')),
    target     TEXT    NOT NULL,
    code_hash  TEXT    NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT    NOT NULL,
    used_at    TEXT,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_codes_user ON verification_codes(user_id, purpose, created_at);

-- To'lovlar: bitta bron uchun bir nechta urinish bo'lishi mumkin, faqat bittasi 'paid'
CREATE TABLE IF NOT EXISTS payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id      INTEGER NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider        TEXT    NOT NULL CHECK (provider IN ('test', 'click', 'payme')),
    amount          INTEGER NOT NULL CHECK (amount > 0),     -- so'm
    status          TEXT    NOT NULL DEFAULT 'created'
                    CHECK (status IN ('created', 'pending', 'paid', 'cancelled', 'refunded', 'refund_pending', 'failed')),
    provider_txn_id TEXT,
    provider_state  INTEGER,
    provider_time   INTEGER,                                 -- Payme: millisekund
    reason          INTEGER,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    paid_at         TEXT,
    cancelled_at    TEXT,
    -- Bekor qilish siyosati: qancha qaytariladi va qolgan qism kimga tegishli (komissiya / owner)
    refund_amount   INTEGER NOT NULL DEFAULT 0,
    kept_commission INTEGER NOT NULL DEFAULT 0,
    kept_payout     INTEGER NOT NULL DEFAULT 0,
    UNIQUE (provider, provider_txn_id)
);
CREATE INDEX IF NOT EXISTS ix_payments_booking ON payments(booking_id, status);

-- Owner'larga o'tkazilgan pullar (admin belgilaydi)
CREATE TABLE IF NOT EXISTS payouts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount     INTEGER NOT NULL CHECK (amount > 0),
    note       TEXT,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Owner'ning pul yechish so'rovlari: owner so'raydi, admin o'tkazib tasdiqlaydi yoki sababini yozib rad etadi.
-- Karta raqami to'liq saqlanmaydi (faqat oxirgi 4 raqam) — maxfiy moliyaviy ma'lumot bazaga tushmaydi.
CREATE TABLE IF NOT EXISTS payout_requests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount       INTEGER NOT NULL CHECK (amount > 0),
    method       TEXT    NOT NULL CHECK (method IN ('card', 'bank', 'cash')),
    card_last4   TEXT    CHECK (card_last4 IS NULL OR length(card_last4) = 4),
    note         TEXT,
    status       TEXT    NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'paid', 'rejected', 'cancelled')),
    admin_note   TEXT,
    payout_id    INTEGER REFERENCES payouts(id) ON DELETE SET NULL,
    processed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    processed_at TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_payout_req ON payout_requests(owner_id, status);

-- Joyida to'langan ijaralar komissiyasi: owner platformaga qarzdor. Qarz naqd to'lanadi yoki owner balansidan ushlanadi.
CREATE TABLE IF NOT EXISTS fee_settlements (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount       INTEGER NOT NULL CHECK (amount > 0),
    from_balance INTEGER NOT NULL DEFAULT 0,          -- 1 = onlayn balansdan ushlandi (payouts'da ham yozuv bor)
    note         TEXT,
    created_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Shikoyatlar: e'lon, sharh, foydalanuvchi yoki xabar ustidan
CREATE TABLE IF NOT EXISTS reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_type TEXT    NOT NULL CHECK (target_type IN ('car', 'review', 'user', 'message')),
    target_id   INTEGER NOT NULL,
    reason      TEXT    NOT NULL CHECK (reason IN ('fake', 'fraud', 'abuse', 'wrong_info', 'spam', 'other')),
    comment     TEXT,
    status      TEXT    NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'resolved', 'dismissed')),
    resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    resolved_at TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_reports_status ON reports(status, created_at);

-- Test pochta qutisi: email/SMS provayderi ulanmaganda (faqat dev/demo) xatlar shu yerga yoziladi
CREATE TABLE IF NOT EXISTS dev_outbox (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel    TEXT NOT NULL,
    to_addr    TEXT NOT NULL,
    subject    TEXT,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Nizolar: bron ishtirokchilari o'rtasidagi muammo (shikast, kelmaslik, depozit...). Admin ikki tomonni eshitib qaror chiqaradi.
CREATE TABLE IF NOT EXISTS disputes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id    INTEGER NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    opened_by     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    against_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type          TEXT    NOT NULL CHECK (type IN ('damage', 'no_show', 'late_return', 'deposit', 'not_as_described', 'payment',
                                                   'fuel_mileage', 'other')),
    description   TEXT    NOT NULL,
    amount        INTEGER CHECK (amount IS NULL OR amount >= 0),
    status        TEXT    NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_review', 'resolved', 'rejected', 'cancelled')),
    response      TEXT,
    response_at   TEXT,
    outcome       TEXT    CHECK (outcome IS NULL OR outcome IN ('favor_opener', 'favor_other', 'split', 'rejected')),
    decision_note TEXT,
    compensation  INTEGER CHECK (compensation IS NULL OR compensation >= 0),
    resolved_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    resolved_at   TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_disputes_status ON disputes(status, created_at);
CREATE INDEX IF NOT EXISTS ix_disputes_booking ON disputes(booking_id);

-- SMS/email yuborish jurnali: matn va kod saqlanmaydi, faqat kimga (yashirilgan), shablon va natija
CREATE TABLE IF NOT EXISTS message_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    channel     TEXT NOT NULL,
    to_masked   TEXT NOT NULL,
    template    TEXT NOT NULL,
    status      TEXT NOT NULL,          -- queued | sent | delivered | failed | dev
    error       TEXT,
    provider_id TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT
);
CREATE INDEX IF NOT EXISTS ix_message_log ON message_log(created_at);

-- Admin va xavfsizlik amallari jurnali (faqat qo'shiladi)
CREATE TABLE IF NOT EXISTS audit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action      TEXT    NOT NULL,
    target_type TEXT,
    target_id   INTEGER,
    details     TEXT,
    ip          TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_audit_created ON audit_logs(created_at);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DB_PATH, timeout=10, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


# Eski bazalarni yangilash: yetishmayotgan ustunlar qo'shiladi (ma'lumot o'chmaydi)
MIGRATIONS = {
    "users": {
        "phone_norm": "TEXT", "email_verified": "INTEGER NOT NULL DEFAULT 0", "phone_verified": "INTEGER NOT NULL DEFAULT 0",
        "avatar": "TEXT", "show_phone": "INTEGER NOT NULL DEFAULT 1", "notify_prefs": "TEXT NOT NULL DEFAULT '{}'",
        "deleted_at": "TEXT", "district": "TEXT",
    },
    "car_images": {"label": "TEXT NOT NULL DEFAULT 'other'"},
    "cars": {"district": "TEXT"},
    "payments": {"refund_amount": "INTEGER NOT NULL DEFAULT 0", "kept_commission": "INTEGER NOT NULL DEFAULT 0",
                 "kept_payout": "INTEGER NOT NULL DEFAULT 0"},
}


def _migrate(conn) -> None:
    for table, cols in MIGRATIONS.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, ddl in cols.items():
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    # Hudud nomlari kanonik ko'rinishga ("Toshkent" -> "Toshkent shahri"): filtr va tumanlar ro'yxati to'g'ri ishlashi uchun
    from .regions import normalize_region
    for table, col in (("cars", "city"), ("users", "region")):
        for (old,) in conn.execute(f"SELECT DISTINCT {col} FROM {table} WHERE {col} IS NOT NULL").fetchall():
            new = normalize_region(old)
            if new and new != old:
                conn.execute(f"UPDATE {table} SET {col} = ? WHERE {col} = ?", (new, old))
    # Telefon bilan kirish uchun normallashtirilgan raqam yagona bo'lishi kerak
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_phone ON users(phone_norm) WHERE phone_norm IS NOT NULL")


def init_db() -> None:
    conn = connect()
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        _migrate(conn)
    finally:
        conn.close()


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection, immediate: bool = False) -> Iterator[None]:
    """immediate=True -> yozish qulfini darhol oladi (ikki kishi bir vaqtda bron qilishining oldini oladi)."""
    conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def rows(cursor) -> list[dict]:
    return [dict(r) for r in cursor.fetchall()]


def one(cursor) -> dict | None:
    r = cursor.fetchone()
    return dict(r) if r else None


def get_setting(db, key: str, default: str = "") -> str:
    r = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return r[0] if r else default
