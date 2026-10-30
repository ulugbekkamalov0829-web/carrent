"""Ilovaning kirish nuqtasi: marshrutlar, middleware'lar, xatolarni qayta ishlash, statik fayllar."""
import logging
import mimetypes
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

from .config import settings
from .db import init_db
from .i18n import current_lang, detect_lang, tr
from .routes import auth, bookings, cars, dashboard, payments, smart, social
from .utils import ApiValidationError

log = logging.getLogger("carrent")
mimetypes.add_type("application/manifest+json", ".webmanifest")

SECURITY_HEADERS = {
    b"x-content-type-options": b"nosniff",
    b"x-frame-options": b"DENY",
    b"referrer-policy": b"strict-origin-when-cross-origin",
    b"permissions-policy": b"camera=(), microphone=(), geolocation=()",
    b"content-security-policy": (
        b"default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
        b"script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; "
        b"object-src 'none'; manifest-src 'self'; worker-src 'self'"
    ),
    b"cross-origin-opener-policy": b"same-origin",
    b"cross-origin-resource-policy": b"same-origin",
}
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# To'lov provayderlari serverdan-serverga chaqiradi: ularda CSRF sarlavhasi yo'q, o'rniga imzo/parol tekshiriladi
CSRF_EXEMPT = ("/api/payments/click", "/api/payments/payme")
UPLOAD_PATHS = ("/images", "/avatar")


class BodyTooLarge(Exception):
    pass


class SecurityMiddleware:
    """1) Har javobga xavfsizlik sarlavhalarini qo'shadi.
    2) CSRF himoyasi: API'ga o'zgartiruvchi so'rovlar faqat 'X-Requested-With' sarlavhasi bilan qabul qilinadi.
       Begona sayt brauzer orqali bunday sarlavha qo'sha olmaydi (CORS buni taqiqlaydi)."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        headers = dict(scope.get("headers") or [])
        # So'rov tili: `lang` cookie yoki Accept-Language -> server xabarlari shu tilda qaytadi
        current_lang.set(detect_lang(headers.get(b"cookie", b"").decode("latin-1"),
                                     headers.get(b"accept-language", b"").decode("latin-1")))
        path = scope["path"]
        if scope["method"] in UNSAFE_METHODS and path.startswith("/api/"):
            if headers.get(b"x-requested-with") != b"fetch" and not path.startswith(CSRF_EXEMPT):
                resp = JSONResponse({"detail": tr("CSRF tekshiruvidan o'tmadi")}, status_code=403)
                return await resp(scope, receive, send)
            # So'rov hajmi chegarasi (DoS'dan himoya): JSON uchun 64 KB, rasm yuklash uchun 25 MB
            limit = settings.MAX_UPLOAD_BODY if path.endswith(UPLOAD_PATHS) else settings.MAX_JSON_BODY
            try:
                declared = int(headers.get(b"content-length", b"0") or 0)
            except ValueError:
                declared = 0
            if declared > limit:
                resp = JSONResponse({"detail": tr("So'rov hajmi juda katta")}, status_code=413)
                return await resp(scope, receive, send)
            received = {"n": 0}
            inner_receive = receive

            async def receive():  # Content-Length ko'rsatilmagan oqimli so'rovlar uchun ham sanaymiz
                message = await inner_receive()
                if message["type"] == "http.request":
                    received["n"] += len(message.get("body", b""))
                    if received["n"] > limit:
                        raise BodyTooLarge()
                return message

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                hdrs = list(message.get("headers", []))
                existing = {k.lower() for k, _ in hdrs}
                for k, v in SECURITY_HEADERS.items():
                    if k not in existing:
                        hdrs.append((k, v))
                if scope["path"].startswith("/api/"):
                    hdrs.append((b"cache-control", b"no-store"))
                if settings.COOKIE_SECURE:
                    hdrs.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                message["headers"] = hdrs
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except BodyTooLarge:
            resp = JSONResponse({"detail": tr("So'rov hajmi juda katta")}, status_code=413)
            await resp(scope, receive, send)


async def http_error(request: Request, exc: HTTPException):
    if not request.url.path.startswith("/api/") and exc.status_code == 404:
        page = settings.STATIC_DIR / "404.html"
        from starlette.responses import FileResponse
        return FileResponse(page, status_code=404)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


async def validation_error(request: Request, exc: ApiValidationError):
    first = exc.errors[0] if exc.errors else {"msg": tr("Ma'lumotlar noto'g'ri")}
    return JSONResponse({"detail": first["msg"], "errors": exc.errors}, status_code=422)


async def server_error(request: Request, exc: Exception):
    log.exception("Kutilmagan xato: %s %s", request.method, request.url.path)
    return JSONResponse({"detail": tr("Serverda kutilmagan xato yuz berdi")}, status_code=500)


async def health(request: Request):
    return JSONResponse({"status": "ok"})


async def moved(request: Request):
    """Eski sahifalar birlashtirildi: Biz haqimizda, Tariflar, Aloqa -> Ma'lumot markazi."""
    return RedirectResponse("/info.html", status_code=301)


async def api_not_found(request: Request):
    raise HTTPException(404, tr("API manzili topilmadi"))


@asynccontextmanager
async def lifespan(app):
    init_db()
    log.info("Ma'lumotlar bazasi tayyor: %s", settings.DB_PATH)
    yield


def create_app() -> Starlette:
    routes = [
        Route("/api/health", health),
        Route("/about.html", moved),
        *auth.routes, *cars.routes, *bookings.routes, *social.routes, *dashboard.routes, *smart.routes, *payments.routes,
        Route("/api/{rest:path}", api_not_found, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]),
        Mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads"),
        Mount("/", StaticFiles(directory=settings.STATIC_DIR, html=True), name="static"),
    ]
    return Starlette(
        debug=False,
        routes=routes,
        middleware=[Middleware(SecurityMiddleware), Middleware(GZipMiddleware, minimum_size=800)],
        exception_handlers={HTTPException: http_error, ApiValidationError: validation_error, Exception: server_error},
        lifespan=lifespan,
    )


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
