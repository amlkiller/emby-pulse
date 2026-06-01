import sys

from app.domains.system import pro as _impl

sys.modules[__name__] = _impl
