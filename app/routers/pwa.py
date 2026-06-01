"""Compatibility shim for the PWA router."""

import sys

from app.domains.pwa import router as _impl

sys.modules[__name__] = _impl
