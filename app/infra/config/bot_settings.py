from typing import Any

from app.core.config import cfg


def get_all_bot_settings() -> dict:
    return cfg.get_all()


def get_bot_setting_source(field: str) -> str:
    return cfg.get_env_source(field)


def get_webhook_token() -> str:
    return cfg.get("webhook_token", "")


def get_tg_bot_token() -> str:
    return cfg.get("tg_bot_token", "")


def get_tg_chat_id() -> str:
    return cfg.get("tg_chat_id", "")


def get_webhook_base_url() -> str:
    return cfg.get("emby_public_url", "") or cfg.get("emby_host", "")


def should_update_sensitive_bot_setting(field: str, value: Any) -> bool:
    if get_bot_setting_source(field) == "env":
        return False
    if not value or str(value).strip() == "":
        return False
    return "****" not in str(value)


def get_bot_settings_audit_values() -> dict:
    return {
        "tg_bot_token": cfg.get("tg_bot_token"),
        "tg_user_bot_token": cfg.get("tg_user_bot_token"),
        "wecom_corpsecret": cfg.get("wecom_corpsecret"),
        "wecom_token": cfg.get("wecom_token"),
        "wecom_aeskey": cfg.get("wecom_aeskey"),
        "enable_bot": cfg.get("enable_bot"),
        "user_bot_open_reg": cfg.get("user_bot_open_reg"),
    }


def set_bot_setting(field: str, value: Any) -> None:
    cfg.set(field, value)


def get_user_bot_token() -> str:
    return cfg.get("tg_user_bot_token")


def get_wecom_aeskey() -> str:
    return cfg.get("wecom_aeskey") or ""


def get_wecom_token() -> str:
    return cfg.get("wecom_token") or ""
