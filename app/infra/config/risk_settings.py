from app.core.config import cfg


_MAX_DEVICES_DEFAULT = 10
_DEFAULT_MAX_CONCURRENT_DEFAULT = 2
_MIN_LIMIT = 1
_VIOLATION_ACTION_DEFAULT = "warn_only"
_VIOLATION_ACTIONS = {"warn_only", "warn_user", "auto_ban"}


def _coerce_positive_int(value, default: int) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return max(_MIN_LIMIT, normalized)


def _coerce_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    return default


def _coerce_violation_action(value) -> str:
    normalized = str(value or "").strip()
    if normalized in _VIOLATION_ACTIONS:
        return normalized
    return _VIOLATION_ACTION_DEFAULT


def get_max_devices() -> int:
    return _coerce_positive_int(cfg.get("max_devices", _MAX_DEVICES_DEFAULT), _MAX_DEVICES_DEFAULT)


def get_default_max_concurrent() -> int:
    return _coerce_positive_int(
        cfg.get("default_max_concurrent", _DEFAULT_MAX_CONCURRENT_DEFAULT),
        _DEFAULT_MAX_CONCURRENT_DEFAULT,
    )


def is_risk_control_enabled() -> bool:
    return _coerce_bool(cfg.get("enable_risk_control", True), True)


def get_violation_action() -> str:
    return _coerce_violation_action(cfg.get("violation_action", _VIOLATION_ACTION_DEFAULT))


def is_risk_sys_notification_enabled() -> bool:
    return _coerce_bool(cfg.get("enable_risk_sys_notification", True), True)


def set_risk_control_enabled(enabled: bool) -> None:
    cfg.set("enable_risk_control", _coerce_bool(enabled, True))


def set_default_max_concurrent(value: int) -> None:
    cfg.set("default_max_concurrent", _coerce_positive_int(value, _DEFAULT_MAX_CONCURRENT_DEFAULT))


def set_violation_action(value: str) -> None:
    cfg.set("violation_action", _coerce_violation_action(value))


def set_risk_sys_notification_enabled(enabled: bool) -> None:
    cfg.set("enable_risk_sys_notification", _coerce_bool(enabled, True))
