from app.core.config import cfg


def get_max_devices() -> int:
    return int(cfg.get("max_devices", 10))


def get_default_max_concurrent() -> int:
    return int(cfg.get("default_max_concurrent", 2))


def is_risk_control_enabled() -> bool:
    return cfg.get("enable_risk_control", True)


def get_violation_action() -> str:
    return cfg.get("violation_action", "warn_only")


def is_risk_sys_notification_enabled() -> bool:
    return cfg.get("enable_risk_sys_notification", True)


def set_risk_control_enabled(enabled: bool) -> None:
    cfg.set("enable_risk_control", enabled)


def set_default_max_concurrent(value: int) -> None:
    cfg.set("default_max_concurrent", value)


def set_violation_action(value: str) -> None:
    cfg.set("violation_action", value)


def set_risk_sys_notification_enabled(enabled: bool) -> None:
    cfg.set("enable_risk_sys_notification", enabled)
