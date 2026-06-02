from app.core.config import cfg


_WEATHER_SOURCE_DEFAULT = "wttr"
_WEATHER_SOURCES = {"wttr", "qweather", "amap"}


def _coerce_weather_source(value) -> str:
    if isinstance(value, bool):
        return _WEATHER_SOURCE_DEFAULT
    normalized = str(value or "").strip().lower()
    if normalized in _WEATHER_SOURCES:
        return normalized
    return _WEATHER_SOURCE_DEFAULT


def get_weather_source() -> str:
    return _coerce_weather_source(cfg.get("weather_source", _WEATHER_SOURCE_DEFAULT))


def get_weather_qweather_key() -> str:
    return cfg.get("weather_qweather_key", "")


def get_weather_qweather_host() -> str:
    return cfg.get("weather_qweather_host", "").strip().rstrip("/")


def get_weather_qweather_host_raw() -> str:
    return cfg.get("weather_qweather_host", "")


def get_weather_amap_key() -> str:
    return cfg.get("weather_amap_key", "")


def get_weather_greeting() -> str:
    return cfg.get("weather_greeting", "")


def set_weather_greeting(value: str) -> None:
    cfg.set("weather_greeting", value)


def set_weather_source(value: str) -> None:
    cfg.set("weather_source", _coerce_weather_source(value))


def set_weather_qweather_host(value: str) -> None:
    cfg.set("weather_qweather_host", value)


def set_weather_qweather_key(value: str) -> None:
    cfg.set("weather_qweather_key", value)


def set_weather_amap_key(value: str) -> None:
    cfg.set("weather_amap_key", value)
