"""Administrator yaratish (ro'yxatdan o'tish sahifasi orqali admin bo'lib bo'lmaydi — bu xavfsizlik uchun).

Ishlatish:  python -m scripts.create_admin admin@carrent.uz "Ism Familiya"
Parol terminalda so'raladi (ekranda ko'rinmaydi).
"""
import getpass
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import get_db, init_db  # noqa: E402
from app.security import hash_password  # noqa: E402


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    email, name = sys.argv[1].lower(), sys.argv[2]
    password = getpass.getpass("Parol (kamida 12 belgi): ")
    if len(password) < 12:
        sys.exit("Parol juda qisqa")
    if password != getpass.getpass("Parolni takrorlang: "):
        sys.exit("Parollar mos emas")
    init_db()
    with get_db() as db:
        try:
            db.execute("INSERT INTO users (full_name, email, phone, password_hash, role) VALUES (?, ?, '', ?, 'admin')",
                       (name, email, hash_password(password)))
        except sqlite3.IntegrityError:
            sys.exit("Bu email band")
    print("Administrator yaratildi:", email)


if __name__ == "__main__":
    main()
