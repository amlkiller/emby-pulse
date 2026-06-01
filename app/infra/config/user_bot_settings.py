from app.core.config import cfg


def get_user_bot_worker_count() -> int:
    try:
        return max(4, min(int(cfg.get("user_bot_worker_count") or 16), 50))
    except Exception:
        return 16


def get_user_bot_restriction_cache_ttl() -> int:
    try:
        ttl = int(cfg.get("user_bot_restriction_cache_ttl") or 120)
        return max(0, min(ttl, 3600))
    except Exception:
        return 120


def get_user_bot_token() -> str:
    return cfg.get("tg_user_bot_token")


def get_user_bot_registration_batch_used() -> int:
    try:
        return int(cfg.get("user_bot_reg_batch_used", 0) or 0)
    except Exception:
        return 0
