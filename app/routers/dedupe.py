"""Compatibility shim for the playback dedupe router."""

import sys

from app.domains.playback import dedupe as _impl

sys.modules[__name__] = _impl
