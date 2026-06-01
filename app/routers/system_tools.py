import sys

from app.domains.system import system_tools as _impl

sys.modules[__name__] = _impl
