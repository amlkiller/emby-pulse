import sys

from app.domains.users import auth as _impl

sys.modules[__name__] = _impl
