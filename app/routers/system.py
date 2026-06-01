"""Compatibility shim for the system router."""

import sys

from app.domains.system import router as _impl

sys.modules[__name__] = _impl
