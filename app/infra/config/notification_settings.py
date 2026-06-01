from app.core.config import cfg
import json


def get_library_notify_channels() -> str:
    return cfg.get("library_notify_channels", "")


def is_message_bot_notify_enabled() -> bool:
    return cfg.get("msg_bot_notify_enabled", True)


def is_message_bot_reply_enabled() -> bool:
    return cfg.get("msg_bot_reply_enabled", False)


def is_user_bot_configured() -> bool:
    return bool(cfg.get("tg_user_bot_token"))


def get_message_notification_base_url() -> str:
    return cfg.get("base_url", "").strip()


def get_notify_channels() -> str:
    return cfg.get("notify_channels", "")


def get_enable_library_notify() -> bool:
    return cfg.get("enable_library_notify", False)


def get_enable_notify() -> bool:
    return cfg.get("enable_notify", False)


def get_notify_user_login() -> bool:
    return cfg.get("notify_user_login", False)


def get_notify_item_deleted() -> bool:
    return cfg.get("notify_item_deleted", False)


def get_tg_bot_token() -> str:
    return cfg.get("tg_bot_token", "")


def get_wecom_corpid() -> str:
    return cfg.get("wecom_corpid", "")


def get_wecom_corpsecret() -> str:
    return cfg.get("wecom_corpsecret", "")


def get_wecom_agentid() -> str:
    return cfg.get("wecom_agentid", "")


def get_wecom_touser() -> str:
    return cfg.get("wecom_touser", "@all")


def get_pulse_url() -> str:
    return cfg.get("pulse_url", "")


def get_wecom_webhook() -> str:
    return cfg.get("wecom_webhook", cfg.get("wechat_webhook", ""))


def _get_notification_channels_config(*, masked: bool) -> dict:
    def mask_token(value):
        if not value or not isinstance(value, str):
            return value
        if len(value) <= 8:
            return "****"
        return value[:4] + "****" + value[-4:]

    return {
        "tg_bot": {
            "token": mask_token(cfg.get("tg_bot_token", "")) if masked else cfg.get("tg_bot_token", ""),
            "chat_id": cfg.get("tg_chat_id", ""),
            "enabled": cfg.get("enable_bot", False),
        },
        "tg_channels": json.loads(cfg.get("notify_channels", "[]")),
        "wecom": {
            "webhook": mask_token(cfg.get("wecom_webhook", cfg.get("wechat_webhook", ""))) if masked else cfg.get("wecom_webhook", cfg.get("wechat_webhook", "")),
            "enabled": cfg.get("enable_wecom", cfg.get("enable_wechat", False)),
        },
    }


def get_notification_channels_config() -> dict:
    return _get_notification_channels_config(masked=True)


def get_notification_channels_runtime_config() -> dict:
    return _get_notification_channels_config(masked=False)


def get_wecom_runtime_config() -> dict:
    return {
        "corpid": cfg.get("wecom_corpid", ""),
        "corpsecret": cfg.get("wecom_corpsecret", ""),
        "agentid": cfg.get("wecom_agentid", ""),
        "touser": cfg.get("wecom_touser", "@all"),
    }


def get_notify_bot_runtime_config() -> dict:
    return {
        "tg_bot_token": cfg.get("tg_bot_token", ""),
        "tg_chat_id": cfg.get("tg_chat_id", ""),
        "wecom_corpid": cfg.get("wecom_corpid", ""),
    }


def set_notification_channels_config(data: dict) -> None:
    def should_update(value):
        if not value or not isinstance(value, str):
            return False
        return "****" not in value

    if "tg_bot" in data:
        token = data["tg_bot"].get("token", "")
        if should_update(token):
            cfg.config["tg_bot_token"] = token
        cfg.config["tg_chat_id"] = data["tg_bot"].get("chat_id", "")
        cfg.config["enable_bot"] = data["tg_bot"].get("enabled", False)

    if "tg_channels" in data:
        cfg.config["notify_channels"] = json.dumps(data["tg_channels"])

    if "wecom" in data:
        webhook = data["wecom"].get("webhook", "")
        if should_update(webhook):
            cfg.config["wecom_webhook"] = webhook
        cfg.config["enable_wecom"] = data["wecom"].get("enabled", False)

    cfg.save()


def set_message_bot_notify_enabled(enabled: bool) -> None:
    cfg.set("msg_bot_notify_enabled", enabled)


def set_message_bot_reply_enabled(enabled: bool) -> None:
    cfg.set("msg_bot_reply_enabled", enabled)
