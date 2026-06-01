from app.core.config import cfg


def is_redirect_to_community_enabled() -> bool:
    value = cfg.get("register_redirect_to_community", "false")
    if isinstance(value, bool):
        return value
    return str(value).lower() == "true"


def get_redirect_to_community_value():
    return cfg.get("register_redirect_to_community", "false")


def get_user_portal_url() -> str:
    return cfg.get("user_portal_url", "")


def get_client_download_url() -> str:
    return cfg.get("client_download_url", "")


def get_client_download_url_or_default() -> str:
    return cfg.get("client_download_url") or "https://emby.media/download.html"


def get_pulse_url() -> str:
    return cfg.get("pulse_url", "")


def set_redirect_to_community_enabled(enabled) -> None:
    if isinstance(enabled, bool):
        cfg.set("register_redirect_to_community", "true" if enabled else "false")
    else:
        cfg.set("register_redirect_to_community", str(enabled))


def set_user_portal_url(value: str) -> None:
    cfg.set("user_portal_url", value)


def set_client_download_url(value: str) -> None:
    cfg.set("client_download_url", value)


def set_pulse_url(value: str) -> None:
    cfg.set("pulse_url", value)
