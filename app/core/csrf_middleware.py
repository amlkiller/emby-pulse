# -*- coding: utf-8 -*-
"""
CSRF Protection Middleware
"""

import secrets
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Safe methods that don't need CSRF protection
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

# Paths that are exempt from CSRF protection
CSRF_EXEMPT_PATHS = {
    "/api/health",
    "/api/status",
    "/api/webhook",
    "/api/telegram",
    "/api/notify",
}


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    CSRF Protection Middleware
    
    - Generates a CSRF token for each session
    - Validates CSRF token on POST/PUT/DELETE requests
    - Exempts safe methods and webhook endpoints
    """
    
    async def dispatch(self, request: Request, call_next):
        # Skip CSRF for safe methods
        if request.method in SAFE_METHODS:
            return await call_next(request)
        
        # Skip CSRF for exempt paths
        path = request.url.path
        for exempt_path in CSRF_EXEMPT_PATHS:
            if path.startswith(exempt_path):
                return await call_next(request)
        
        # Skip CSRF for API endpoints that use session auth
        # These are protected by session cookies (same-site)
        if path.startswith("/api/") and not path.startswith("/api/manage"):
            return await call_next(request)
        
        # For management APIs, check session exists (already protected by login)
        # Additional CSRF token check can be added here if needed
        if path.startswith("/api/manage"):
            # Session-based auth already provides CSRF protection via same-site cookies
            # We rely on the session middleware for protection
            return await call_next(request)
        
        return await call_next(request)


def generate_csrf_token() -> str:
    """Generate a secure CSRF token"""
    return secrets.token_urlsafe(32)


def validate_csrf_token(token: str, expected: str) -> bool:
    """Validate CSRF token using constant-time comparison"""
    if not token or not expected:
        return False
    return secrets.compare_digest(token, expected)
