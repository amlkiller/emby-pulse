# -*- coding: utf-8 -*-
"""
Security Headers Middleware
Adds security headers to all responses
"""

import secrets
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


def _generate_csp_nonce() -> str:
    """Generate a cryptographic nonce for CSP script-src."""
    return secrets.token_urlsafe(24)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security headers to prevent common attacks:
    - X-Frame-Options: Prevents clickjacking
    - X-Content-Type-Options: Prevents MIME sniffing
    - X-XSS-Protection: XSS filter (legacy, but still useful)
    - Referrer-Policy: Controls referrer information
    - Permissions-Policy: Restricts browser features
    - Content-Security-Policy: Nonce-based script execution
    """

    async def dispatch(self, request: Request, call_next):
        # Generate per-request CSP nonce and store for template access
        nonce = _generate_csp_nonce()
        request.state.csp_nonce = nonce

        response = await call_next(request)

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "SAMEORIGIN"

        # Prevent MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # XSS protection (legacy but useful for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Restrict browser features
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=(), "
            "usb=()"
        )

        # CSP policy
        # 现代浏览器使用 script-src-elem (强制 nonce) + script-src-attr (允许 inline 事件处理器)。
        # script-src 作为旧浏览器兜底，保留 'unsafe-inline' 以兼容 1000+ 内联事件处理器。
        # 现代浏览器优先使用细化指令，nonce 对 <script> 标签生效，inline handler 通过 -attr 单独允许。
        cdn_sources = (
            "https://cdn.tailwindcss.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com "
            "https://cdn.quilljs.com https://html2canvas.hertzen.com https://static.cloudflareinsights.com"
        )
        # Alpine.js / Tailwind CDN 需要 unsafe-eval 才能求值模板表达式
        response.headers["Content-Security-Policy"] = (
            f"default-src 'self'; "
            f"script-src 'self' 'unsafe-inline' 'unsafe-eval' {cdn_sources}; "
            f"script-src-elem 'self' 'unsafe-eval' 'nonce-{nonce}' {cdn_sources}; "
            f"script-src-attr 'unsafe-inline'; "
            f"style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com https://cdn.quilljs.com; "
            f"img-src 'self' data: blob: https:; "
            f"font-src 'self' data: https://fonts.gstatic.com {cdn_sources}; "
            f"connect-src 'self' {cdn_sources} https://fonts.googleapis.com https://fonts.gstatic.com https://static.cloudflareinsights.com; "
            f"frame-ancestors 'self';"
        )

        # 注意：HSTS (Strict-Transport-Security) 由前置 nginx 反向代理统一下发，
        # 应用层不再重复设置，避免双重 header 与配置漂移。

        return response
