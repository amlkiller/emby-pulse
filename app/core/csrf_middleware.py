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
    "/api/requests/register",
}


def _same_origin(url1: str, url2: str) -> bool:
    """严格同源比较：scheme + netloc 完全相等"""
    try:
        u1 = urlparse(url1)
        u2 = urlparse(url2)
        return (u1.scheme, u1.netloc) == (u2.scheme, u2.netloc) and bool(u1.netloc)
    except Exception:
        return False


def _expected_origins(request: Request) -> list:
    """计算允许的同源 URL 列表

    反向代理场景下 base_url 返回的是内部 scheme+host，与浏览器看到的
    公网 URL 不一致。因此在 base_url 之外，再纳入 X-Forwarded-Proto/Host
    （以及 X-Forwarded-Port）所组合的对外 URL 作为合法源。

    X-Forwarded-* 由反向代理设置；攻击者无法通过浏览器伪造受害者请求里
    的 Origin/Referer，所以即使这些头存在，CSRF 防护仍然有效。
    """
    origins = []

    # 1) 直连场景：用 base_url（scheme + netloc）
    try:
        base = str(request.base_url).rstrip("/")
        if base:
            origins.append(base)
    except Exception:
        pass

    # 2) 反代场景：组合 X-Forwarded-* 头
    fwd_host = request.headers.get("x-forwarded-host") or request.headers.get("x-original-host")
    fwd_proto = request.headers.get("x-forwarded-proto")
    fwd_port = request.headers.get("x-forwarded-port")
    if fwd_host:
        # 多个值时取第一个
        host = fwd_host.split(",")[0].strip()
        proto = (fwd_proto.split(",")[0].strip() if fwd_proto else "https")
        # 若 host 已含端口则忽略 X-Forwarded-Port，否则在非默认端口时拼接
        if ":" not in host and fwd_port:
            port = fwd_port.split(",")[0].strip()
            if (proto == "http" and port != "80") or (proto == "https" and port != "443"):
                host = f"{host}:{port}"
        origins.append(f"{proto}://{host}")

    # 3) 兜底：直接拿 Host 头（保持原 scheme 假设为 http/https 两种都接受）
    host_header = request.headers.get("host")
    if host_header:
        # base_url 已经覆盖了原始 scheme + host，这里仅作为最后兜底
        origins.append(f"https://{host_header}")
        origins.append(f"http://{host_header}")

    return origins


def _origin_allowed(origin: str, expected: list) -> bool:
    return any(_same_origin(origin, e) for e in expected if e)


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
        # 同时识别管理端 (session["user"]) 与用户端 (session["req_user"])
        session = request.scope.get("session", {})
        if session.get("user") or session.get("req_user"):
            if request.method in ("POST", "PUT", "DELETE", "PATCH"):
                origin = request.headers.get("origin", "")
                referer = request.headers.get("referer", "")
                expected = _expected_origins(request)
                if origin:
                    if not _origin_allowed(origin, expected):
                        return JSONResponse(status_code=403, content={"detail": "CSRF 验证失败：Origin 不匹配"})
                elif referer:
                    if not _origin_allowed(referer, expected):
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
