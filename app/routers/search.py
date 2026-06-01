"""Compatibility shim for the playback search router."""

import sys

from app.domains.playback import search as _impl

sys.modules[__name__] = _impl
