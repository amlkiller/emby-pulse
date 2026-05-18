# -*- coding: utf-8 -*-
"""
CSRF Protection Middleware
"""

from urllib.parse import urlparse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from app.core.jwt_token import verify_api_token

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

# 精确豁免路径：仅外部 Webhook 与登录注册入口
# 注意：不再使用 /api/bot 或 /api/telegram 整前缀豁免，避免管理接口被绕过 CSRF
CSRF_EXEMPT_PATHS = {
    "/api/v1/webhook",
    "/api/bot/webhook",
    "/api/bot/wecom_webhook",
    "/api/telegram/webhook",
    "/api/login",
    "/api/register",
    "/api/requests/auth",
}


def _same_origin(url1: str, url2: str) -> bool:
    """严格同源比较：scheme + netloc 完全相等"""
    try:
        u1 = urlparse(url1)
        u2 = urlparse(url2)
        return (u1.scheme, u1.netloc) == (u2.scheme, u2.netloc) and bool(u1.netloc)
    except Exception:
        return False


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 安全方法不校验
        if request.method in SAFE_METHODS:
            return await call_next(request)

        path = request.url.path

        # 豁免路径：精确匹配（含尾部斜杠或查询参数的同路径）
        if path in CSRF_EXEMPT_PATHS or any(
            path == p or path.startswith(p + "/") for p in CSRF_EXEMPT_PATHS
        ):
            return await call_next(request)

        # 豁免有效的 API Token 请求
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            payload = verify_api_token(token)
            if payload:
                return await call_next(request)

        # 已登录用户的 session 请求 — 验证 Origin/Referer 防 CSRF
        session = request.scope.get("session", {})
        if session.get("user"):
            if request.method in ("POST", "PUT", "DELETE", "PATCH"):
                origin = request.headers.get("origin", "")
                referer = request.headers.get("referer", "")
                host = str(request.base_url).rstrip("/")
                if origin:
                    if not _same_origin(origin, host):
                        return JSONResponse(status_code=403, content={"detail": "CSRF 验证失败：Origin 不匹配"})
                elif referer:
                    if not _same_origin(referer, host):
                        return JSONResponse(status_code=403, content={"detail": "CSRF 验证失败：Referer 不匹配"})
                else:
                    # 同源 POST 浏览器默认带 Origin；都缺失视为可疑
                    return JSONResponse(status_code=403, content={"detail": "CSRF 验证失败：缺少 Origin/Referer"})
            return await call_next(request)

        # 未登录用户的非豁免 POST 请求 → 拒绝
        return JSONResponse(
            status_code=403,
            content={"detail": "CSRF 验证失败：请先登录"}
        )
