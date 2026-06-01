"""Compatibility shim for the system webhook router."""

import sys

from app.domains.system import webhook as _impl

sys.modules[__name__] = _impl
