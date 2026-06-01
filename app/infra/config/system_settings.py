from typing import Any

from app.core.config import cfg
from app.infra.config.bot_settings import get_webhook_token
from app.infra.config.db_settings import get_playback_data_mode
from app.infra.config.media_server_settings import (
    get_media_server_api_key,
    get_media_server_host,
    get_media_server_main_public_or_host,
    get_media_server_public_url,
    get_media_server_type,
    get_media_server_welcome_message,
)
from app.infra.config.moviepilot_settings import get_moviepilot_url
from app.infra.config.notification_settings import (
    get_notify_item_deleted,
    get_notify_user_login,
)
from app.infra.config.proxy_settings import get_proxy_url
from app.infra.config.tmdb_settings import get_tmdb_api_key
from app.infra.config.user_visibility_settings import get_hidden_users
from app.infra.config.weather_settings import (
    get_weather_amap_key,
    get_weather_qweather_host,
    get_weather_qweather_key,
    get_weather_source,
)


def get_system_config_value(field: str, default=""):
    return cfg.get(field, default)


def get_system_config_env_source(field: str) -> str:
    return cfg.get_env_source(field)


def set_system_config_value(field: str, value: Any) -> None:
    cfg.set(field, value)


def get_system_server_type() -> str:
    return get_media_server_type()


def get_system_emby_host() -> str:
    return get_media_server_host()


def get_system_proxy_url() -> str:
    return get_proxy_url()


def get_system_hidden_users() -> list:
    return get_hidden_users()


def get_system_emby_public_url() -> str:
    return get_media_server_public_url()


def get_system_welcome_message() -> str:
    return get_media_server_welcome_message()


def get_system_moviepilot_url() -> str:
    return get_moviepilot_url()


def get_system_playback_data_mode() -> str:
    return get_playback_data_mode()


def get_system_notify_user_login() -> bool:
    return get_notify_user_login()


def get_system_notify_item_deleted() -> bool:
    return get_notify_item_deleted()


def get_system_weather_greeting() -> str:
    return cfg.get("weather_greeting", "")


def get_system_weather_source() -> str:
    return get_weather_source()


def get_system_weather_qweather_host() -> str:
    return get_weather_qweather_host()


def get_system_webhook_token() -> str:
    return get_webhook_token()


def get_system_emby_api_key() -> str:
    return get_media_server_api_key()


def get_system_tmdb_api_key() -> str:
    return get_tmdb_api_key()


def get_system_weather_qweather_key() -> str:
    return get_weather_qweather_key()


def get_system_weather_amap_key() -> str:
    return get_weather_amap_key()


def get_system_emby_public_or_host() -> str:
    return get_media_server_main_public_or_host()
