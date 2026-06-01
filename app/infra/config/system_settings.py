from typing import Any

from app.core.config import cfg


def get_system_config_value(field: str, default: Any = "") -> Any:
    return cfg.get(field, default)


def get_system_config_env_source(field: str) -> str:
    return cfg.get_env_source(field)


def set_system_config_value(field: str, value: Any) -> None:
    cfg.set(field, value)


def get_system_server_type() -> str:
    return cfg.get("server_type", "emby")


def get_system_emby_host() -> str:
    return cfg.get("emby_host")


def get_system_proxy_url() -> str:
    return cfg.get("proxy_url")


def get_system_hidden_users() -> list:
    return cfg.get("hidden_users") or []


def get_system_emby_public_url() -> str:
    return cfg.get("emby_public_url", "")


def get_system_welcome_message() -> str:
    return cfg.get("welcome_message", "")


def get_system_moviepilot_url() -> str:
    return cfg.get("moviepilot_url", "")


def get_system_playback_data_mode() -> str:
    return cfg.get("playback_data_mode", "sqlite")


def get_system_notify_user_login() -> bool:
    return cfg.get("notify_user_login", False)


def get_system_notify_item_deleted() -> bool:
    return cfg.get("notify_item_deleted", False)


def get_system_weather_greeting() -> str:
    return cfg.get("weather_greeting", "")


def get_system_weather_source() -> str:
    return cfg.get("weather_source", "wttr")


def get_system_weather_qweather_host() -> str:
    return cfg.get("weather_qweather_host", "")


def get_system_webhook_token() -> str:
    return cfg.get("webhook_token", "")


def get_system_emby_api_key() -> str:
    return cfg.get("emby_api_key")


def get_system_tmdb_api_key() -> str:
    return cfg.get("tmdb_api_key")


def get_system_weather_qweather_key() -> str:
    return cfg.get("weather_qweather_key")


def get_system_weather_amap_key() -> str:
    return cfg.get("weather_amap_key")


def get_system_emby_public_or_host() -> str:
    return cfg.get("emby_public_url", "") or cfg.get("emby_host", "")
