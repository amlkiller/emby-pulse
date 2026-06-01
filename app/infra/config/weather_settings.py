from app.core.config import cfg


def get_weather_source() -> str:
    return cfg.get("weather_source", "wttr")


def get_weather_qweather_key() -> str:
    return cfg.get("weather_qweather_key", "")


def get_weather_qweather_host() -> str:
    return cfg.get("weather_qweather_host", "").strip().rstrip("/")


def get_weather_amap_key() -> str:
    return cfg.get("weather_amap_key", "")
