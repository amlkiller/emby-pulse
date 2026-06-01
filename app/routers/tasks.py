import sys

from app.domains.system import tasks as _impl

sys.modules[__name__] = _impl
