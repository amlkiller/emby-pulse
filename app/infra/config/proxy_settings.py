from app.core.config import cfg


def get_proxy_url() -> str:
    return cfg.get("proxy_url") or ""


def get_wecom_proxy_url() -> str:
    return cfg.get("wecom_proxy_url") or ""
