import os

from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.csrf_middleware import CSRFMiddleware
from app.core.rate_limiter import RateLimitMiddleware
from app.core.security_headers_middleware import SecurityHeadersMiddleware
from app.core.session_middleware import DatabaseSessionMiddleware


class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        is_no_cache_path = (
            request.url.path.endswith(".html")
            or request.url.path.startswith("/api/")
            or request.url.path == "/"
            or request.url.path.startswith("/request")
            or request.url.path.startswith("/login")
            or request.url.path.startswith("/register")
        )
        if is_no_cache_path:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            response.headers["Vary"] = "Cookie, Authorization"
        return response


def _resolve_allowed_origins() -> list[str]:
    cors_env = os.getenv("CORS_ORIGINS", "").strip()
    if not cors_env:
        print("🔒 [安全] CORS 未配置跨域来源，已拒绝所有跨域请求（如需开放请设置 CORS_ORIGINS 环境变量）")
        return []

    allowed_origins = [origin.strip() for origin in cors_env.split(",") if origin.strip()]
    dangerous = [origin for origin in allowed_origins if origin in ("*", "null")]
    if dangerous:
        print(f"🔒 [安全] CORS_ORIGINS 包含危险值 {dangerous}，已忽略")
        allowed_origins = [origin for origin in allowed_origins if origin not in ("*", "null")]
    if allowed_origins:
        print(f"🔒 [安全] CORS 已配置允许的来源: {allowed_origins}")
    else:
        print("🔒 [安全] CORS_ORIGINS 无有效值，已拒绝所有跨域请求")
    return allowed_origins


def configure_middlewares(app) -> None:
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(DatabaseSessionMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_resolve_allowed_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Requested-With",
            "X-Telegram-Bot-Api-Secret-Token",
        ],
    )
    app.add_middleware(NoCacheMiddleware)

