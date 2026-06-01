from app.core.config import cfg


def is_message_bot_notify_enabled() -> bool:
    return cfg.get("msg_bot_notify_enabled", True)


def is_message_bot_reply_enabled() -> bool:
    return cfg.get("msg_bot_reply_enabled", False)


def is_user_bot_configured() -> bool:
    return bool(cfg.get("tg_user_bot_token"))


def get_message_notification_base_url() -> str:
    return cfg.get("base_url", "").strip()


def set_message_bot_notify_enabled(enabled: bool) -> None:
    cfg.set("msg_bot_notify_enabled", enabled)


def set_message_bot_reply_enabled(enabled: bool) -> None:
    cfg.set("msg_bot_reply_enabled", enabled)
