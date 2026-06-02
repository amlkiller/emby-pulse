from app.core.config import cfg


_PLAYBACK_DATA_MODE_DEFAULT = "sqlite"
_PLAYBACK_DATA_MODES = {"sqlite", "api"}
_SLOW_QUERY_MS_DEFAULT = 800
_MIN_SLOW_QUERY_MS = 1


def _coerce_playback_data_mode(value) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _PLAYBACK_DATA_MODES:
        return normalized
    return _PLAYBACK_DATA_MODE_DEFAULT


def _coerce_positive_int(value, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return max(_MIN_SLOW_QUERY_MS, normalized)


def get_playback_data_mode() -> str:
    return _coerce_playback_data_mode(cfg.get("playback_data_mode", _PLAYBACK_DATA_MODE_DEFAULT))


def set_playback_data_mode(value: str) -> None:
    cfg.set("playback_data_mode", _coerce_playback_data_mode(value))


def get_slow_query_ms() -> int:
    return _coerce_positive_int(cfg.get("slow_query_ms", _SLOW_QUERY_MS_DEFAULT), _SLOW_QUERY_MS_DEFAULT)
