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
        # 安全方法不校验
        if request.method in SAFE_METHODS:
            return await call_next(request)

        path = request.url.path

        # 豁免路径：webhook、bot、登录注册
        for exempt in CSRF_EXEMPT_PATHS:
            if path.startswith(exempt):
                return await call_next(request)

        # 豁免有效的 API Token 请求
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")
            from app.core.jwt_token import verify_api_token
            payload = verify_api_token(token)
            if payload:
                return await call_next(request)

        # 豁免已登录用户的 session 请求（SameSite cookie 已提供 CSRF 保护）
        session = request.scope.get("session", {})
        if session.get("user"):
            return await call_next(request)

        # 未登录用户的非豁免 POST 请求 → 拒绝
        return JSONResponse(
            status_code=403,
            content={"detail": "CSRF 验证失败：请先登录"}
        )
