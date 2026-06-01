from app.core.config import cfg


def get_default_max_concurrent() -> int:
    return int(cfg.get("default_max_concurrent", 2))


def is_risk_control_enabled() -> bool:
    return cfg.get("enable_risk_control", True)


def get_violation_action() -> str:
    return cfg.get("violation_action", "warn_only")


def is_risk_sys_notification_enabled() -> bool:
    return cfg.get("enable_risk_sys_notification", True)
