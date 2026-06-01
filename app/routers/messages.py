import sys

from app.domains.notifications import messages as _impl

sys.modules[__name__] = _impl
