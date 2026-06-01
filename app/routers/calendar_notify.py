import sys

from app.domains.notifications import calendar_notify as _impl

sys.modules[__name__] = _impl
