import sys

from app.domains.notifications import user_bot_service as _impl

sys.modules[__name__] = _impl
