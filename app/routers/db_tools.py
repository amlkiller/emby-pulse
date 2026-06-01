"""Compatibility shim for the system database tools router."""

import sys

from app.domains.system import db_tools as _impl

sys.modules[__name__] = _impl
