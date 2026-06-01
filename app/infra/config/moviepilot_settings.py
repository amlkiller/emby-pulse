from app.core.config import cfg


def get_moviepilot_url() -> str:
    return cfg.get("moviepilot_url", "")


def get_moviepilot_token() -> str:
    return cfg.get("moviepilot_token", "")


def set_moviepilot_url(value: str) -> None:
    cfg.set("moviepilot_url", value)


def set_moviepilot_token(value: str) -> None:
    cfg.set("moviepilot_token", value)
