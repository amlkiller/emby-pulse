import sys

from app.domains.notifications import bot as _impl

sys.modules[__name__] = _impl
