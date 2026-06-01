import sys

from app.domains.system import views as _impl

sys.modules[__name__] = _impl
