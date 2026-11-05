"""Doimiy saqlash: Supabase Storage (bepul) — Render bepul diski har uyg'onishda tozalanadi.

Ishlash tartibi:
  * server yonayotganda: bazaning oxirgi nusxasi va barcha yuklangan fayllar Storage'dan tiklanadi;
  * ishlab turganda: har BACKUP_EVERY_SEC soniyada baza o'zgarganmi tekshiriladi — o'zgargan bo'lsa,
    SQLite'ning izchil nusxasi (backup API) olinadi va yuklanadi; yangi rasm/hujjat fayllari ham yuklanadi;
  * to'xtayotganda: oxirgi marta nusxa olinadi.
Hech qanday qo'shimcha kutubxona kerak emas (faqat HTTPS). Kalit (service_role) faqat serverda — brauzerga hech qachon berilmaydi.
Bucket "private" yaratiladi: fayllarga faqat shu kalit bilan kirish mumkin.
"""
import json
import logging
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .config import settings

log = logging.getLogger("carrent.persist")
_lock = threading.Lock()
_state = {"sig": None, "files": set(), "last_ok": None, "last_error": None, "uploads": 0}
_stop = threading.Event()


def enabled() -> bool:
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY)


def _req(method: str, path: str, data: bytes | None = None, ctype: str = "application/json", extra: dict | None = None,
         timeout: int = 60) -> bytes:
    url = f"{settings.SUPABASE_URL}/storage/v1/{path}"
    headers = {"Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}", "apikey": settings.SUPABASE_SERVICE_KEY}
    if data is not None:
        headers["Content-Type"] = ctype
    headers.update(extra or {})
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _bucket() -> str:
    return urllib.parse.quote(settings.SUPABASE_BUCKET)


def ensure_bucket() -> None:
    try:
        _req("GET", f"bucket/{_bucket()}")
    except urllib.error.HTTPError as e:
        if e.code not in (400, 404):
            raise
        body = json.dumps({"id": settings.SUPABASE_BUCKET, "name": settings.SUPABASE_BUCKET, "public": False}).encode()
        _req("POST", "bucket", body)
        log.info("Supabase bucket yaratildi: %s", settings.SUPABASE_BUCKET)


def upload(key: str, content: bytes, ctype: str = "application/octet-stream") -> None:
    _req("POST", f"object/{_bucket()}/{urllib.parse.quote(key)}", content, ctype, {"x-upsert": "true"}, timeout=120)


def download(key: str) -> bytes | None:
    try:
        return _req("GET", f"object/{_bucket()}/{urllib.parse.quote(key)}", timeout=120)
    except urllib.error.HTTPError as e:
        if e.code in (400, 404):
            return None
        raise


def list_keys(prefix: str) -> list[str]:
    out, offset = [], 0
    while True:
        body = json.dumps({"prefix": prefix, "limit": 1000, "offset": offset, "sortBy": {"column": "name", "order": "asc"}}).encode()
        items = json.loads(_req("POST", f"object/list/{_bucket()}", body) or b"[]")
        out += [f"{prefix}{i['name']}" for i in items if i.get("id")]   # papkalarda id bo'lmaydi
        if len(items) < 1000:
            return out
        offset += 1000


FOLDERS = (("uploads/", lambda: settings.UPLOAD_DIR), ("private/", lambda: settings.PRIVATE_DIR))


def restore() -> None:
    """Server yonishida: bazani va fayllarni tiklash (bazaga hali hech kim ulanmagan payt)."""
    if not enabled():
        return
    try:
        ensure_bucket()
        data = download("db/app.db")
        if data:
            tmp = settings.DB_PATH.with_suffix(".restore")
            tmp.write_bytes(data)
            for ext in ("", "-wal", "-shm"):
                Path(str(settings.DB_PATH) + ext).unlink(missing_ok=True)
            tmp.replace(settings.DB_PATH)
            log.info("Baza Supabase'dan tiklandi (%d KB)", len(data) // 1024)
        else:
            log.info("Supabase'da baza nusxasi yo'q — yangi baza bilan boshlanadi")
        n = 0
        for prefix, folder in FOLDERS:
            for key in list_keys(prefix):
                target = folder() / key[len(prefix):]
                if "/" in key[len(prefix):] or target.exists():
                    _state["files"].add(key)
                    continue
                content = download(key)
                if content is not None:
                    target.write_bytes(content)
                    n += 1
                _state["files"].add(key)
        log.info("Supabase'dan %d ta fayl tiklandi", n)
        _state["sig"] = _db_signature()
        _state["last_ok"] = time.time()
    except Exception as e:  # tarmoq xatosi serverni to'xtatmasin
        _state["last_error"] = str(e)
        log.exception("Supabase'dan tiklashda xato")


def _db_signature():
    sig = []
    for ext in ("", "-wal"):
        p = Path(str(settings.DB_PATH) + ext)
        if p.exists():
            st = p.stat()
            sig.append((st.st_size, st.st_mtime_ns))
    return tuple(sig)


def backup_now(force: bool = False) -> bool:
    if not enabled():
        return False
    with _lock:
        try:
            # 1) yangi fayllar (rasm, hujjat) — bir marta yuklanadi
            for prefix, folder in FOLDERS:
                for f in folder().iterdir():
                    key = prefix + f.name
                    if f.is_file() and key not in _state["files"]:
                        upload(key, f.read_bytes())
                        _state["files"].add(key)
            # 2) baza o'zgargan bo'lsa — izchil nusxa
            sig = _db_signature()
            if force or sig != _state["sig"]:
                snap = settings.DATA_DIR / "snapshot.db"
                src = sqlite3.connect(settings.DB_PATH, timeout=10)
                dst = sqlite3.connect(snap)
                try:
                    src.backup(dst)
                finally:
                    dst.close(); src.close()
                upload("db/app.db", snap.read_bytes())
                snap.unlink(missing_ok=True)
                _state["sig"] = sig
                _state["uploads"] += 1
            _state["last_ok"], _state["last_error"] = time.time(), None
            return True
        except Exception as e:
            _state["last_error"] = str(e)
            log.warning("Supabase'ga nusxa olishda xato: %s", e)
            return False


def _loop():
    while not _stop.wait(settings.BACKUP_EVERY_SEC):
        backup_now()


def start() -> None:
    if enabled():
        threading.Thread(target=_loop, name="supabase-backup", daemon=True).start()
        log.info("Supabase doimiy saqlash yoqilgan (har %d soniyada)", settings.BACKUP_EVERY_SEC)


def stop() -> None:
    _stop.set()
    backup_now()


def status() -> dict:
    return {"enabled": enabled(), "last_ok": _state["last_ok"], "last_error": _state["last_error"], "uploads": _state["uploads"],
            "files": len(_state["files"]), "bucket": settings.SUPABASE_BUCKET if enabled() else None}
