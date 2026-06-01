import sys

from app.domains.notifications import notify_rules as _impl

sys.modules[__name__] = _impl
