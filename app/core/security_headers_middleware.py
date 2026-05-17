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

        # CSP with nonce-based script execution (no 'unsafe-inline')
        response.headers["Content-Security-Policy"] = (
            f"default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}' https://cdn.tailwindcss.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            f"style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
            f"img-src 'self' data: blob: https:; "
            f"font-src 'self' data: https://fonts.gstatic.com; "
            f"connect-src 'self'; "
            f"frame-ancestors 'self';"
        )

        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response
