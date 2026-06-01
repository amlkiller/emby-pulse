from app.core.config import cfg


def get_media_server_host() -> str:
    return cfg.get("emby_host", "").rstrip("/")


def get_media_server_public_url() -> str:
    return cfg.get("emby_public_url", "") or cfg.get("emby_host", "")


def get_media_server_public_host() -> str:
    return cfg.get("emby_public_host") or cfg.get("emby_host", "")


def get_media_server_external_url() -> str:
    return cfg.get("emby_external_url") or ""


def get_media_server_routes() -> list:
    return cfg.get_all_routes()


def get_media_server_user_routes(user_id: str) -> list:
    return cfg.get_user_routes(user_id)


def get_media_server_main_public_url() -> str:
    return cfg.get_main_public_url() or ""


def get_media_server_main_public_or_host() -> str:
    return cfg.get_main_public_url() or cfg.get("emby_host", "")


def get_media_server_api_key() -> str:
    return cfg.get("emby_api_key", "")


def get_media_server_type() -> str:
    return cfg.get("server_type", "emby").lower()


def get_media_server_welcome_message() -> str:
    return cfg.get("welcome_message", "")
