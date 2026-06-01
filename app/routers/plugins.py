"""Compatibility shim for the plugins router."""

import sys

from app.domains.plugins import router as _impl

sys.modules[__name__] = _impl
