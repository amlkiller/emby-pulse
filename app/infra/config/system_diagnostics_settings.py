import os
from typing import Any

from app.core.config import cfg


SENSITIVE_ENV_FIELDS = {
    "tg_bot_token": "TG_BOT_TOKEN",
    "tg_user_bot_token": "TG_USER_BOT_TOKEN",
    "emby_api_key": "EMBY_API_KEY",
    "tmdb_api_key": "TMDB_API_KEY",
    "webhook_token": "WEBHOOK_TOKEN",
    "moviepilot_token": "MOVIEPILOT_TOKEN",
    "wecom_corpsecret": "WECOM_CORPSECRET",
    "wecom_token": "WECOM_TOKEN",
    "wecom_aeskey": "WECOM_AESKEY",
}


SYSTEM_SETTINGS_SENSITIVE_FIELDS = [
    "emby_api_key",
    "tmdb_api_key",
    "moviepilot_token",
    "weather_qweather_key",
    "weather_amap_key",
]


def get_sensitive_env_fields() -> dict[str, str]:
    return dict(SENSITIVE_ENV_FIELDS)


def get_system_settings_sensitive_fields() -> list[str]:
    return list(SYSTEM_SETTINGS_SENSITIVE_FIELDS)


def get_config_value(field: str, default: Any = "") -> Any:
    return cfg.get(field, default)


def get_config_env_source(field: str) -> str:
    return cfg.get_env_source(field)


def get_env_value(env_key: str, default: str = "") -> str:
    return os.getenv(env_key, default)


def is_env_managed_setting(field: str) -> bool:
    return get_config_env_source(field) == "env"


def should_update_sensitive_setting(field: str, value: Any) -> bool:
    if is_env_managed_setting(field):
        return False
    if not value or str(value).strip() == "":
        return False
    return "****" not in str(value)
