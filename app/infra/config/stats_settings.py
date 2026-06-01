from app.core.config import cfg


def get_dashboard_cache_ttl() -> int:
    try:
        return int(cfg.get("dashboard_cache_ttl") or 300)
    except Exception:
        return 300
