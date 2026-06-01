from app.core.config import cfg


def get_calendar_cache_ttl() -> int:
    return int(cfg.get("calendar_cache_ttl") or 86400)
