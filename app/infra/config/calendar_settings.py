from app.core.config import cfg


def get_calendar_cache_ttl() -> int:
    return int(cfg.get("calendar_cache_ttl") or 86400)


def set_calendar_cache_ttl(value: int) -> None:
    cfg.set("calendar_cache_ttl", value)


def get_calendar_public_url() -> str:
    return cfg.get("emby_public_url") or cfg.get("emby_public_host") or cfg.get("emby_host")
