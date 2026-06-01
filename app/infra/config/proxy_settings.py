from app.core.config import cfg


def get_proxy_url() -> str:
    return cfg.get("proxy_url") or ""


def get_proxy_url_raw() -> str:
    return cfg.get("proxy_url")


def set_proxy_url(value: str) -> None:
    cfg.set("proxy_url", value)


def get_wecom_proxy_url() -> str:
    return cfg.get("wecom_proxy_url") or ""
