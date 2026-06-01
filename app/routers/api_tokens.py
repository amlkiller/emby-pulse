"""Compatibility shim for the system API token router."""

import sys

from app.domains.system import api_tokens as _impl

sys.modules[__name__] = _impl
