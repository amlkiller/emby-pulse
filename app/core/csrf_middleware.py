# -*- coding: utf-8 -*-
"""
CSRF Protection Middleware
"""

import secrets
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

CSRF_EXEMPT_PATHS = {
    "/api/v1/webhook",
    "/api/telegram",
    "/api/bot",
    "/api/auth/login",
    "/api/auth/register",
}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in SAFE_METHODS:
            return await call_next(request)

        path = request.url.path

        for exempt in CSRF_EXEMPT_PATHS:
            if path.startswith(exempt):
                return await call_next(request)

        if request.headers.get("Authorization"):
            return await call_next(request)

        csrf_token = request.headers.get("X-CSRF-Token")
        session = request.scope.get("session", {})
        expected = session.get("csrf_token")

        if not csrf_token or not expected or not secrets.compare_digest(csrf_token, expected):
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF 验证失败"}
            )

        return await call_next(request)
