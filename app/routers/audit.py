import sys

from app.domains.system import audit as _impl

sys.modules[__name__] = _impl
