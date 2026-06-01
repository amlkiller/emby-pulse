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


def set_user_bot_token(value: str) -> None:
    cfg.set("tg_user_bot_token", value)


def is_user_bot_restriction_enabled() -> bool:
    return cfg.get("user_bot_restriction_enabled", False)


def get_user_bot_required_channels() -> str:
    return cfg.get("user_bot_required_channels", "")


def get_user_bot_required_groups() -> str:
    return cfg.get("user_bot_required_groups", "")


def get_user_bot_registration_batch_used() -> int:
    try:
        return int(cfg.get("user_bot_reg_batch_used", 0) or 0)
    except Exception:
        return 0


def set_user_bot_registration_batch_used(value: int) -> None:
    cfg.set("user_bot_reg_batch_used", value)


def is_user_bot_open_reg_enabled() -> bool:
    return cfg.get("user_bot_open_reg", False)


def set_user_bot_open_reg_enabled(enabled: bool) -> None:
    cfg.set("user_bot_open_reg", enabled)


def get_user_bot_open_reg_enabled() -> bool:
    return is_user_bot_open_reg_enabled()


def is_user_bot_open_reg_notify_user_enabled() -> bool:
    return cfg.get("user_bot_open_reg_notify_user", False)


def is_user_bot_open_reg_notify_group_enabled() -> bool:
    return cfg.get("user_bot_open_reg_notify_group", False)


def set_user_bot_open_reg_notify_user_enabled(enabled: bool) -> None:
    cfg.set("user_bot_open_reg_notify_user", enabled)


def set_user_bot_open_reg_notify_group_enabled(enabled: bool) -> None:
    cfg.set("user_bot_open_reg_notify_group", enabled)


def get_user_bot_allowed_groups() -> str:
    return cfg.get("user_bot_allowed_groups", "")


def set_user_bot_allowed_groups(value: str) -> None:
    cfg.set("user_bot_allowed_groups", value)


def get_user_bot_reg_quota_mode() -> str:
    return cfg.get("user_bot_reg_quota_mode", "total")


def set_user_bot_reg_quota_mode(value: str) -> None:
    cfg.set("user_bot_reg_quota_mode", value)


def get_user_bot_reg_quota() -> int:
    try:
        return int(cfg.get("user_bot_reg_quota", 0) or 0)
    except Exception:
        return 0


def get_user_bot_group_enabled() -> bool:
    return cfg.get("user_bot_group_enabled", False)


def set_user_bot_group_enabled(enabled: bool) -> None:
    cfg.set("user_bot_group_enabled", enabled)


def get_user_bot_group_commands() -> str:
    return cfg.get("user_bot_group_commands", "checkin,help")


def set_user_bot_group_commands(value: str) -> None:
    cfg.set("user_bot_group_commands", value)


def get_user_bot_welcome_msg() -> str:
    return cfg.get("user_bot_welcome_msg", "")


def set_user_bot_welcome_msg(value: str) -> None:
    cfg.set("user_bot_welcome_msg", value)


def get_user_bot_portal_url() -> str:
    return cfg.get("user_bot_portal_url")


def set_user_bot_portal_url(value: str) -> None:
    cfg.set("user_bot_portal_url", value)


def get_user_bot_route_mode() -> str:
    return cfg.get("user_bot_route_mode", "block")


def set_user_bot_route_mode(value: str) -> None:
    cfg.set("user_bot_route_mode", value)


def get_user_bot_allow_routes() -> str:
    return cfg.get("user_bot_allow_routes", "")


def set_user_bot_allow_routes(value: str) -> None:
    cfg.set("user_bot_allow_routes", value)


def get_user_bot_block_routes() -> str:
    return cfg.get("user_bot_block_routes", "")


def set_user_bot_block_routes(value: str) -> None:
    cfg.set("user_bot_block_routes", value)


def get_user_bot_max_reg() -> int:
    try:
        return int(cfg.get("user_bot_max_reg", 0))
    except Exception:
        return 0


def get_user_bot_reg_days() -> int:
    try:
        return int(cfg.get("user_bot_reg_days", 30))
    except Exception:
        return 30


def get_user_bot_template_user() -> str:
    return cfg.get("user_bot_template_user") or cfg.get("default_user_template_id")


def set_user_bot_template_user(value: str) -> None:
    cfg.set("user_bot_template_user", value)


def get_user_bot_notify_user_enabled() -> bool:
    return is_user_bot_open_reg_notify_user_enabled()


def get_user_bot_notify_group_enabled() -> bool:
    return is_user_bot_open_reg_notify_group_enabled()
