from app.core.config import cfg
from app.infra.config.media_server_settings import (
    get_media_server_api_key,
    get_media_server_host,
)


def is_local_auth_enabled() -> bool:
    return cfg.get("enable_local_auth", False)


def is_emby_auth_disabled() -> bool:
    return cfg.get("disable_emby_auth", False)


def set_local_auth_enabled(enabled: bool) -> None:
    cfg.set("enable_local_auth", enabled)


def set_emby_auth_disabled(disabled: bool) -> None:
    cfg.set("disable_emby_auth", disabled)


def is_media_server_configured() -> bool:
    return bool(get_media_server_host() and get_media_server_api_key())
