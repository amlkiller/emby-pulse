"""Compatibility shim for the playback insight router."""

import sys

from app.domains.playback import insight as _impl

sys.modules[__name__] = _impl
