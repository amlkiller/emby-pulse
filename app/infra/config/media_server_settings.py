from app.core.config import cfg


def get_media_server_host() -> str:
    return cfg.get("emby_host", "").rstrip("/")


def get_media_server_public_url() -> str:
    return cfg.get("emby_public_url", "") or cfg.get("emby_host", "")


def get_media_server_api_key() -> str:
    return cfg.get("emby_api_key", "")


def get_media_server_type() -> str:
    return cfg.get("server_type", "emby").lower()
