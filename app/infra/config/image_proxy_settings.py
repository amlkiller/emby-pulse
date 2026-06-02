from app.core.config import cfg
from app.infra.config.coercion import coerce_positive_int


_IMAGE_PROXY_MAX_BYTES_DEFAULT = 10 * 1024 * 1024


def get_image_proxy_max_bytes() -> int:
    return coerce_positive_int(
        cfg.get("image_proxy_max_bytes", _IMAGE_PROXY_MAX_BYTES_DEFAULT),
        _IMAGE_PROXY_MAX_BYTES_DEFAULT,
    )
