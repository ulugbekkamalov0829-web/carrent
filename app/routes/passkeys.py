"""Barmoq izi / yuz bilan kirish (WebAuthn passkey) — bank ilovalaridagidek.

Telefonning o'zi barmoq izini tekshiradi; serverga barmoq izi emas, faqat ochiq kalit va imzo keladi.
Ro'yxatdan o'tkazish (bir marta, parol bilan kirgandan keyin) va kirish ikki bosqichli: avval server "challenge"
(tasodifiy bir martalik qiymat) beradi, qurilma uni yopiq kalit bilan imzolaydi, server ochiq kalit bilan tekshiradi.
Faqat HTTPS (yoki localhost) sahifada ishlaydi.
"""
import base64
import hashlib
import json
import secrets
import struct
import time

try:   # "cryptography" o'rnatilmagan bo'lsa ham sayt ishlayveradi — faqat barmoq izi bilan kirish o'chiq bo'ladi
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
    CRYPTO_OK = True
except ImportError:  # pragma: no cover
    CRYPTO_OK = False
from pydantic import Field
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.routing import Route

from ..db import get_db, one, rows
from ..i18n import tr
from ..schemas import Base
from ..security import client_ip, login_limiter, require
from ..utils import ok, parse_body, path_int
from .auth import _login_response

CHALLENGE_TTL = 180
_challenges: dict[str, tuple[int | None, float, str]] = {}   # challenge -> (user_id, muddat, maqsad)


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def unb64u(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ---------- kichik CBOR o'quvchi (WebAuthn uchun yetarli qism) ----------
def cbor_decode(data: bytes, pos: int = 0):
    ib = data[pos]; pos += 1
    major, info = ib >> 5, ib & 31
    if info < 24:
        val = info
    elif info == 24:
        val = data[pos]; pos += 1
    elif info == 25:
        val = struct.unpack(">H", data[pos:pos + 2])[0]; pos += 2
    elif info == 26:
        val = struct.unpack(">I", data[pos:pos + 4])[0]; pos += 4
    elif info == 27:
        val = struct.unpack(">Q", data[pos:pos + 8])[0]; pos += 8
    else:
        raise ValueError("CBOR: noaniq uzunlik qo'llab-quvvatlanmaydi")
    if major == 0:
        return val, pos
    if major == 1:
        return -1 - val, pos
    if major == 2:
        return data[pos:pos + val], pos + val
    if major == 3:
        return data[pos:pos + val].decode(), pos + val
    if major == 4:
        out = []
        for _ in range(val):
            item, pos = cbor_decode(data, pos); out.append(item)
        return out, pos
    if major == 5:
        out = {}
        for _ in range(val):
            k, pos = cbor_decode(data, pos)
            v, pos = cbor_decode(data, pos)
            out[k] = v
        return out, pos
    if major == 7:
        return {20: False, 21: True, 22: None}.get(info), pos
    raise ValueError("CBOR: tur qo'llab-quvvatlanmaydi")


def cose_to_pem(cose: dict) -> tuple[bytes, int]:
    """COSE kalit -> PEM ochiq kalit va algoritm (-7 ES256 yoki -257 RS256)."""
    kty, alg = cose.get(1), cose.get(3)
    if kty == 2 and alg == -7:
        x, y = cose[-2], cose[-3]
        key = ec.EllipticCurvePublicNumbers(int.from_bytes(x, "big"), int.from_bytes(y, "big"), ec.SECP256R1()).public_key()
    elif kty == 3 and alg == -257:
        key = rsa.RSAPublicNumbers(int.from_bytes(cose[-2], "big"), int.from_bytes(cose[-1], "big")).public_key()
    else:
        raise HTTPException(400, tr("Bu qurilmaning kalit turi qo'llab-quvvatlanmaydi"))
    return key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo), alg


def verify_sig(pem: bytes, alg: int, sig: bytes, data: bytes) -> bool:
    key = serialization.load_pem_public_key(pem)
    try:
        if alg == -7:
            key.verify(sig, data, ec.ECDSA(hashes.SHA256()))
        else:
            key.verify(sig, data, padding.PKCS1v15(), hashes.SHA256())
        return True
    except InvalidSignature:
        return False


def rp_id(request: Request) -> str:
    return (request.headers.get("host") or request.url.hostname or "localhost").split(":")[0]


def _new_challenge(uid: int | None, purpose: str) -> str:
    if not CRYPTO_OK:
        raise HTTPException(503, tr("Barmoq izi bilan kirish serverda yoqilmagan"))
    now = time.time()
    for k in [k for k, v in _challenges.items() if v[1] < now]:
        _challenges.pop(k, None)
    ch = b64u(secrets.token_bytes(32))
    _challenges[ch] = (uid, now + CHALLENGE_TTL, purpose)
    return ch


def _check_client_data(request: Request, raw: bytes, typ: str, purpose: str) -> tuple[dict, int | None]:
    try:
        cd = json.loads(raw)
    except ValueError:
        raise HTTPException(400, tr("Barmoq izi bilan tasdiqlash amalga oshmadi"))
    entry = _challenges.pop(cd.get("challenge", ""), None)
    if cd.get("type") != typ or not entry or entry[1] < time.time() or entry[2] != purpose:
        raise HTTPException(400, tr("So'rov muddati o'tdi. Qayta urinib ko'ring"))
    origin = cd.get("origin", "")
    host = rp_id(request)
    ok_scheme = origin.startswith("https://") or host in ("localhost", "127.0.0.1")
    if not ok_scheme or origin.split("://", 1)[-1].split(":")[0] != host:
        raise HTTPException(400, tr("Barmoq izi bilan tasdiqlash amalga oshmadi"))
    return cd, entry[0]


def _check_auth_data(request: Request, auth: bytes) -> tuple[int, int]:
    if len(auth) < 37 or auth[:32] != hashlib.sha256(rp_id(request).encode()).digest():
        raise HTTPException(400, tr("Barmoq izi bilan tasdiqlash amalga oshmadi"))
    flags = auth[32]
    if not flags & 0x01 or not flags & 0x04:        # foydalanuvchi bor (UP) va barmoq izi/PIN tekshirilgan (UV)
        raise HTTPException(400, tr("Qurilma barmoq izi yoki PIN kodni tekshirmadi"))
    return flags, struct.unpack(">I", auth[33:37])[0]


# ---------------- ro'yxatdan o'tkazish ----------------
@require()
async def register_options(request: Request):
    u = request.state.user
    with get_db() as db:
        mine = rows(db.execute("SELECT cred_id FROM passkeys WHERE user_id = ?", (u["id"],)))
        info = one(db.execute("SELECT email, full_name FROM users WHERE id = ?", (u["id"],)))
    return ok({
        "challenge": _new_challenge(u["id"], "reg"),
        "rp": {"id": rp_id(request), "name": "CarRent"},
        "user": {"id": b64u(str(u["id"]).encode()), "name": info["email"], "displayName": info["full_name"]},
        "pubKeyCredParams": [{"type": "public-key", "alg": -7}, {"type": "public-key", "alg": -257}],
        "timeout": CHALLENGE_TTL * 1000,
        "attestation": "none",
        "authenticatorSelection": {"authenticatorAttachment": "platform", "userVerification": "required",
                                   "residentKey": "required", "requireResidentKey": True},
        "excludeCredentials": [{"type": "public-key", "id": r["cred_id"]} for r in mine],
    })


class RegisterIn(Base):
    id: str = Field(max_length=1400)
    clientDataJSON: str = Field(max_length=4000)
    attestationObject: str = Field(max_length=20000)
    name: str = Field(default="", max_length=60)


@require()
async def register_finish(request: Request):
    data = await parse_body(request, RegisterIn)
    uid = request.state.user["id"]
    _, ch_uid = _check_client_data(request, unb64u(data.clientDataJSON), "webauthn.create", "reg")
    if ch_uid != uid:
        raise HTTPException(400, tr("So'rov muddati o'tdi. Qayta urinib ko'ring"))
    att, _ = cbor_decode(unb64u(data.attestationObject))
    auth = att.get("authData") or b""
    flags, count = _check_auth_data(request, auth)
    if not flags & 0x40:
        raise HTTPException(400, tr("Barmoq izi bilan tasdiqlash amalga oshmadi"))
    cred_len = struct.unpack(">H", auth[53:55])[0]
    cred_id = auth[55:55 + cred_len]
    cose, _ = cbor_decode(auth, 55 + cred_len)
    pem, alg = cose_to_pem(cose)
    if b64u(cred_id) != data.id:
        raise HTTPException(400, tr("Barmoq izi bilan tasdiqlash amalga oshmadi"))
    ua = (request.headers.get("user-agent") or "")
    name = data.name.strip() or ("iPhone" if "iPhone" in ua else "Android" if "Android" in ua else "Mac" if "Mac" in ua
                                 else "Windows" if "Windows" in ua else tr("Qurilma"))
    with get_db() as db:
        db.execute("INSERT INTO passkeys (user_id, cred_id, public_key, alg, sign_count, name) VALUES (?, ?, ?, ?, ?, ?)",
                   (uid, data.id, pem.decode(), alg, count, name[:60]))
    return ok({"saved": True, "name": name}, 201)


# ---------------- kirish ----------------
async def login_options(request: Request):
    return ok({"challenge": _new_challenge(None, "login"), "rpId": rp_id(request), "timeout": CHALLENGE_TTL * 1000,
               "userVerification": "required", "allowCredentials": []})


class LoginIn(Base):
    id: str = Field(max_length=1400)
    clientDataJSON: str = Field(max_length=4000)
    authenticatorData: str = Field(max_length=4000)
    signature: str = Field(max_length=2000)


async def login_finish(request: Request):
    data = await parse_body(request, LoginIn)
    if not login_limiter.hit(f"{client_ip(request)}|passkey"):
        raise HTTPException(429, tr("Juda ko'p urinish. 5 daqiqadan so'ng qayta urinib ko'ring"))
    raw_cd = unb64u(data.clientDataJSON)
    _check_client_data(request, raw_cd, "webauthn.get", "login")
    auth = unb64u(data.authenticatorData)
    _, count = _check_auth_data(request, auth)
    with get_db() as db:
        pk = one(db.execute("SELECT p.*, u.role, u.is_active, u.deleted_at FROM passkeys p JOIN users u ON u.id = p.user_id "
                            "WHERE p.cred_id = ?", (data.id,)))
        if not pk or pk["deleted_at"]:
            raise HTTPException(401, tr("Bu barmoq izi hech qaysi akkauntga ulanmagan. Avval parol bilan kiring"))
        if not pk["is_active"]:
            raise HTTPException(403, tr("Hisobingiz administrator tomonidan bloklangan"))
        signed = auth + hashlib.sha256(raw_cd).digest()
        if not verify_sig(pk["public_key"].encode(), pk["alg"], unb64u(data.signature), signed):
            raise HTTPException(401, tr("Barmoq izi bilan tasdiqlash amalga oshmadi"))
        if count and pk["sign_count"] and count <= pk["sign_count"]:     # kalit nusxalangan bo'lishi mumkin
            raise HTTPException(401, tr("Barmoq izi bilan tasdiqlash amalga oshmadi"))
        db.execute("UPDATE passkeys SET sign_count = ?, last_used = datetime('now') WHERE id = ?", (count, pk["id"]))
        return _login_response(db, pk["user_id"], pk["role"], request)


# ---------------- boshqarish ----------------
@require()
async def my_passkeys(request: Request):
    with get_db() as db:
        return ok({"items": rows(db.execute("SELECT id, name, created_at, last_used FROM passkeys WHERE user_id = ? ORDER BY id DESC",
                                            (request.state.user["id"],)))})


@require()
async def delete_passkey(request: Request):
    with get_db() as db:
        db.execute("DELETE FROM passkeys WHERE id = ? AND user_id = ?", (path_int(request), request.state.user["id"]))
    return await my_passkeys(request)


routes = [
    Route("/api/passkeys", my_passkeys, methods=["GET"]),
    Route("/api/passkeys/{id:int}", delete_passkey, methods=["DELETE"]),
    Route("/api/passkeys/register/options", register_options, methods=["POST"]),
    Route("/api/passkeys/register", register_finish, methods=["POST"]),
    Route("/api/passkeys/login/options", login_options, methods=["POST"]),
    Route("/api/passkeys/login", login_finish, methods=["POST"]),
]
