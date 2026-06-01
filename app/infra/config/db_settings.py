from app.core.config import cfg


def get_playback_data_mode() -> str:
    return cfg.get("playback_data_mode", "sqlite")


def get_slow_query_ms() -> int:
    try:
        return int(cfg.get("slow_query_ms") or 800)
    except Exception:
        return 800
