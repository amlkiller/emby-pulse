from app.core.config import cfg
from app.infra.config.coercion import coerce_positive_int


_DASHBOARD_CACHE_TTL_DEFAULT = 300


def get_dashboard_cache_ttl() -> int:
    return coerce_positive_int(
        cfg.get("dashboard_cache_ttl", _DASHBOARD_CACHE_TTL_DEFAULT),
        _DASHBOARD_CACHE_TTL_DEFAULT,
    )
