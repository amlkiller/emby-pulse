from app.core.config import cfg
from app.infra.config.coercion import coerce_positive_int


_REG_QUOTA_MODE_DEFAULT = "total"
_REG_QUOTA_MODES = {"total", "batch"}
_ROUTE_MODE_DEFAULT = "block"
_ROUTE_MODES = {"block", "allow"}
_REG_DAYS_DEFAULT = 30
_WORKER_COUNT_DEFAULT = 16
_WORKER_COUNT_MIN = 4
_WORKER_COUNT_MAX = 50


def _coerce_enum(value, *, supported: set, default: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in supported:
        return normalized
    return default


def get_user_bot_worker_count() -> int:
    return coerce_positive_int(
        cfg.get("user_bot_worker_count", _WORKER_COUNT_DEFAULT),
        _WORKER_COUNT_DEFAULT,
        minimum=_WORKER_COUNT_MIN,
        maximum=_WORKER_COUNT_MAX,
    )


def get_user_bot_restriction_cache_ttl() -> int:
    try:
        ttl = int(cfg.get("user_bot_restriction_cache_ttl") or 120)
        return max(0, min(ttl, 3600))
    except Exception:
        return 120


def get_user_bot_token() -> str:
    return cfg.get("tg_user_bot_token")


def get_user_bot_token_or_empty() -> str:
    return cfg.get("tg_user_bot_token") or ""


def set_user_bot_token(value: str) -> None:
    cfg.set("tg_user_bot_token", value)


def is_user_bot_restriction_enabled() -> bool:
    return cfg.get("user_bot_restriction_enabled", False)


def get_user_bot_required_channels() -> str:
    return cfg.get("user_bot_required_channels", "")


def get_user_bot_required_groups() -> str:
    return cfg.get("user_bot_required_groups", "")


def get_user_bot_registration_batch_used() -> int:
    return coerce_positive_int(cfg.get("user_bot_reg_batch_used", 0), 0, minimum=0)


def set_user_bot_registration_batch_used(value: int) -> None:
    cfg.set("user_bot_reg_batch_used", coerce_positive_int(value, 0, minimum=0))


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
    return _coerce_enum(
        cfg.get("user_bot_reg_quota_mode", _REG_QUOTA_MODE_DEFAULT),
        supported=_REG_QUOTA_MODES,
        default=_REG_QUOTA_MODE_DEFAULT,
    )


def set_user_bot_reg_quota_mode(value: str) -> None:
    cfg.set(
        "user_bot_reg_quota_mode",
        _coerce_enum(value, supported=_REG_QUOTA_MODES, default=_REG_QUOTA_MODE_DEFAULT),
    )


def get_user_bot_reg_quota() -> int:
    return coerce_positive_int(cfg.get("user_bot_reg_quota", 0), 0, minimum=0)


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
    return _coerce_enum(
        cfg.get("user_bot_route_mode", _ROUTE_MODE_DEFAULT),
        supported=_ROUTE_MODES,
        default=_ROUTE_MODE_DEFAULT,
    )


def set_user_bot_route_mode(value: str) -> None:
    cfg.set(
        "user_bot_route_mode",
        _coerce_enum(value, supported=_ROUTE_MODES, default=_ROUTE_MODE_DEFAULT),
    )


def get_user_bot_allow_routes() -> str:
    return cfg.get("user_bot_allow_routes", "")


def set_user_bot_allow_routes(value: str) -> None:
    cfg.set("user_bot_allow_routes", value)


def get_user_bot_block_routes() -> str:
    return cfg.get("user_bot_block_routes", "")


def set_user_bot_block_routes(value: str) -> None:
    cfg.set("user_bot_block_routes", value)


def get_user_bot_max_reg() -> int:
    return coerce_positive_int(cfg.get("user_bot_max_reg", 0), 0, minimum=0)


def get_user_bot_reg_days() -> int:
    return coerce_positive_int(cfg.get("user_bot_reg_days", _REG_DAYS_DEFAULT), _REG_DAYS_DEFAULT)


def get_user_bot_template_user() -> str:
    return cfg.get("user_bot_template_user") or cfg.get("default_user_template_id")


def set_user_bot_template_user(value: str) -> None:
    cfg.set("user_bot_template_user", value)


def get_default_user_template_id() -> str:
    return cfg.get("default_user_template_id") or ""


def set_default_user_template_id(value: str) -> None:
    cfg.set("default_user_template_id", value)


def get_user_bot_notify_user_enabled() -> bool:
    return is_user_bot_open_reg_notify_user_enabled()


def get_user_bot_notify_group_enabled() -> bool:
    return is_user_bot_open_reg_notify_group_enabled()
