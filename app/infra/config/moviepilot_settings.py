from app.core.config import cfg


def get_moviepilot_url() -> str:
    return cfg.get("moviepilot_url", "")


def get_moviepilot_token() -> str:
    return cfg.get("moviepilot_token", "")
