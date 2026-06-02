from app.core.config import cfg
from app.infra.config.coercion import coerce_positive_int


_CALENDAR_CACHE_TTL_DEFAULT = 86400


def get_calendar_cache_ttl() -> int:
    return coerce_positive_int(cfg.get("calendar_cache_ttl", _CALENDAR_CACHE_TTL_DEFAULT), _CALENDAR_CACHE_TTL_DEFAULT)


def set_calendar_cache_ttl(value: int) -> None:
    cfg.set("calendar_cache_ttl", coerce_positive_int(value, _CALENDAR_CACHE_TTL_DEFAULT))


def get_calendar_public_url() -> str:
    return cfg.get("emby_public_url") or cfg.get("emby_public_host") or cfg.get("emby_host")
