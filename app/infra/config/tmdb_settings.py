from app.core.config import cfg


def get_tmdb_api_key() -> str:
    return cfg.get("tmdb_api_key", "")
