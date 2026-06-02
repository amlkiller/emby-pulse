from app.core.config import cfg
from app.infra.config.coercion import coerce_positive_int


_PLAYBACK_DATA_MODE_DEFAULT = "sqlite"
_PLAYBACK_DATA_MODES = {"sqlite", "api"}
_SLOW_QUERY_MS_DEFAULT = 800


def _coerce_playback_data_mode(value) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _PLAYBACK_DATA_MODES:
        return normalized
    return _PLAYBACK_DATA_MODE_DEFAULT


def get_playback_data_mode() -> str:
    return _coerce_playback_data_mode(cfg.get("playback_data_mode", _PLAYBACK_DATA_MODE_DEFAULT))


def set_playback_data_mode(value: str) -> None:
    cfg.set("playback_data_mode", _coerce_playback_data_mode(value))


def get_slow_query_ms() -> int:
    return coerce_positive_int(cfg.get("slow_query_ms", _SLOW_QUERY_MS_DEFAULT), _SLOW_QUERY_MS_DEFAULT)
