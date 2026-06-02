from typing import Any
import logging
import secrets

from app.core.config import cfg
from app.infra.config.coercion import coerce_positive_int


_BOT_WORKER_COUNT_DEFAULT = 8
_BOT_WORKER_COUNT_MIN = 2
_BOT_WORKER_COUNT_MAX = 32
_LIBRARY_NOTIFY_QUEUE_MAX_DEFAULT = 300
_LIBRARY_NOTIFY_QUEUE_MAX_MIN = 50
_LIBRARY_NOTIFY_QUEUE_MAX_MAX = 2000


def get_bot_worker_count() -> int:
    return coerce_positive_int(
        cfg.get("bot_worker_count", _BOT_WORKER_COUNT_DEFAULT),
        _BOT_WORKER_COUNT_DEFAULT,
        minimum=_BOT_WORKER_COUNT_MIN,
        maximum=_BOT_WORKER_COUNT_MAX,
    )


def get_library_notify_queue_max() -> int:
    return coerce_positive_int(
        cfg.get("library_notify_queue_max", _LIBRARY_NOTIFY_QUEUE_MAX_DEFAULT),
        _LIBRARY_NOTIFY_QUEUE_MAX_DEFAULT,
        minimum=_LIBRARY_NOTIFY_QUEUE_MAX_MIN,
        maximum=_LIBRARY_NOTIFY_QUEUE_MAX_MAX,
    )


def get_all_bot_settings() -> dict:
    return cfg.get_all()


def get_bot_setting_source(field: str) -> str:
    return cfg.get_env_source(field)


def get_webhook_token() -> str:
    return cfg.get("webhook_token", "")


def set_webhook_token(value: str) -> None:
    cfg.set("webhook_token", value)


def ensure_strong_webhook_token() -> None:
    weak_tokens = {"embypulse", "emby", "test", "123456", "password", ""}
    if get_webhook_token() in weak_tokens:
        set_webhook_token(secrets.token_urlsafe(32))
        logging.getLogger("uvicorn").warning("[安全] Webhook Token 已自动生成（原为弱 token），请更新 Emby Webhook 配置")


def get_tg_bot_token() -> str:
    return cfg.get("tg_bot_token", "")


def get_tg_chat_id() -> str:
    return cfg.get("tg_chat_id", "")


def get_webhook_base_url() -> str:
    return cfg.get("emby_public_url", "") or cfg.get("emby_host", "")


def should_update_sensitive_bot_setting(field: str, value: Any) -> bool:
    if get_bot_setting_source(field) == "env":
        return False
    if not value or str(value).strip() == "":
        return False
    return "****" not in str(value)


def get_bot_settings_audit_values() -> dict:
    return {
        "tg_bot_token": cfg.get("tg_bot_token"),
        "tg_user_bot_token": cfg.get("tg_user_bot_token"),
        "wecom_corpsecret": cfg.get("wecom_corpsecret"),
        "wecom_token": cfg.get("wecom_token"),
        "wecom_aeskey": cfg.get("wecom_aeskey"),
        "enable_bot": cfg.get("enable_bot"),
        "user_bot_open_reg": cfg.get("user_bot_open_reg"),
    }


def set_bot_setting(field: str, value: Any) -> None:
    cfg.set(field, value)


def get_user_bot_token() -> str:
    return cfg.get("tg_user_bot_token")


def get_wecom_aeskey() -> str:
    return cfg.get("wecom_aeskey") or ""


def get_wecom_token() -> str:
    return cfg.get("wecom_token") or ""


def is_bot_enabled() -> bool:
    return cfg.get("enable_bot", False)
