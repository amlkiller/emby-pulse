from app.core.config import cfg


def get_image_proxy_max_bytes() -> int:
    try:
        return int(cfg.get("image_proxy_max_bytes") or 10 * 1024 * 1024)
    except Exception:
        return 10 * 1024 * 1024
