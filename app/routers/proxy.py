"""Compatibility shim for the proxy router."""

import sys

from app.domains.proxy import router as _impl

sys.modules[__name__] = _impl
