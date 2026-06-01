from app.core.config import cfg


def get_hidden_users() -> list:
    return cfg.get("hidden_users") or []
