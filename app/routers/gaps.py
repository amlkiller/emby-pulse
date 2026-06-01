import sys

from app.domains.media_requests import gaps as _impl

sys.modules[__name__] = _impl
