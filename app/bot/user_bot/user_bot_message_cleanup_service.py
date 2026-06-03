import threading
import time

from app.infra.clients.telegram_client import telegram_client
from app.infra.config.user_bot_settings import get_user_bot_token
from app.utils.proxy_helper import get_safe_proxies


_threading_provider = lambda: threading
_time_provider = lambda: time
_token_provider = lambda: get_user_bot_token()
_telegram_client_provider = lambda: telegram_client
_safe_proxies_provider = lambda: get_safe_proxies()


def set_dependency_providers(
    *,
    threading_provider=None,
    time_provider=None,
    token_provider=None,
    telegram_client_provider=None,
    safe_proxies_provider=None,
):
    global _threading_provider
    global _time_provider
    global _token_provider
    global _telegram_client_provider
    global _safe_proxies_provider

    if threading_provider is not None:
        _threading_provider = threading_provider
    if time_provider is not None:
        _time_provider = time_provider
    if token_provider is not None:
        _token_provider = token_provider
    if telegram_client_provider is not None:
        _telegram_client_provider = telegram_client_provider
    if safe_proxies_provider is not None:
        _safe_proxies_provider = safe_proxies_provider


def delete_messages_later(chat_id, message_ids, delay_seconds=30):
    """延迟删除消息（用于群聊签到自动清理）"""
    def delete_messages():
        _time_provider().sleep(delay_seconds)
        token = _token_provider()
        if not token:
            return
        for msg_id in message_ids:
            if msg_id:
                try:
                    _telegram_client_provider().post_api(
                        token,
                        "deleteMessage",
                        json={"chat_id": chat_id, "message_id": msg_id},
                        proxies=_safe_proxies_provider(),
                        timeout=10,
                    )
                except Exception:
                    pass

    _threading_provider().Thread(target=delete_messages, daemon=True).start()
