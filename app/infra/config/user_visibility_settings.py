from app.core.config import cfg


def get_hidden_users() -> list:
    return cfg.get("hidden_users") or []


def set_hidden_users(value) -> None:
    cfg.set("hidden_users", value)
