import logging

from app.infra.clients.telegram_client import telegram_client


logger = logging.getLogger("uvicorn")

_logger_provider = lambda: logger
_telegram_client_provider = lambda: telegram_client


def set_dependency_providers(*, logger_provider=None, telegram_client_provider=None):
    global _logger_provider
    global _telegram_client_provider

    if logger_provider is not None:
        _logger_provider = logger_provider
    if telegram_client_provider is not None:
        _telegram_client_provider = telegram_client_provider


def _is_request_hdhive_search_action(data):
    if not data.startswith("req_"):
        return False
    parts = data.split("_")
    return len(parts) > 1 and parts[1] == "hdhive"


def _clear_reply_markup(cid, mid, token, proxies):
    try:
        _telegram_client_provider().post_api(
            token,
            "editMessageReplyMarkup",
            json={"chat_id": cid, "message_id": mid, "reply_markup": {"inline_keyboard": []}},
            proxies=proxies,
            timeout=5,
        )
    except Exception:
        pass


def handle_request_hdhive_search_callback(data, cid, cq_id, mid, token, proxies):
    if not _is_request_hdhive_search_action(data):
        return False

    try:
        from app.plugins.hdhive.plugin import handle_request_hdhive_search

        handle_request_hdhive_search(data, cid, cq_id, "tg")
    except Exception as e:
        _logger_provider().error(f"[Bot] 影巢搜索回调处理失败: {e}")
        _clear_reply_markup(cid, mid, token, proxies)
    return True
