"""Compatibility shim for the playback calendar router."""

import sys

from app.domains.playback import calendar as _impl

sys.modules[__name__] = _impl
