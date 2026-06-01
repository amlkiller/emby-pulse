from app.core.config import cfg


def get_tmdb_api_key() -> str:
    return cfg.get("tmdb_api_key", "")


def set_tmdb_api_key(value: str) -> None:
    cfg.set("tmdb_api_key", value)
