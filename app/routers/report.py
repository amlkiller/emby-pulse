"""Compatibility shim for the reports router."""

import sys

from app.domains.reports import router as _impl

sys.modules[__name__] = _impl
