import sys

from app.domains.system import clients as _impl

sys.modules[__name__] = _impl
