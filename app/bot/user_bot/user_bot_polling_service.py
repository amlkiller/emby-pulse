import logging

from app.infra.clients.telegram_client import telegram_client
from app.utils.proxy_helper import get_safe_proxies


logger = logging.getLogger("uvicorn")

_telegram_client_provider = lambda: telegram_client
_get_safe_proxies_provider = lambda: get_safe_proxies
_submit_task_provider = lambda: (lambda func, *args, **kwargs: False)
_send_provider = lambda: (lambda chat_id, text, reply_markup=None: None)
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    telegram_client_provider=None,
    get_safe_proxies_provider=None,
    submit_task_provider=None,
    send_provider=None,
    logger_provider=None,
):
    global _telegram_client_provider
    global _get_safe_proxies_provider
    global _submit_task_provider
    global _send_provider
    global _logger_provider

    if telegram_client_provider is not None:
        _telegram_client_provider = telegram_client_provider
    if get_safe_proxies_provider is not None:
        _get_safe_proxies_provider = get_safe_proxies_provider
    if submit_task_provider is not None:
        _submit_task_provider = submit_task_provider
    if send_provider is not None:
        _send_provider = send_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def run_polling_loop(
    token,
    running_provider,
    stop_event,
    offset_provider,
    set_offset_callback,
    message_handler_provider,
    callback_handler_provider,
):
    while running_provider() and not stop_event.is_set():
        try:
            res = _telegram_client_provider().get_updates(
                token,
                params={"offset": offset_provider(), "timeout": 30},
                proxies=_get_safe_proxies_provider()(),
                timeout=35,
            )
            if res.status_code == 200:
                updates = res.json().get("result", [])
                for update in updates:
                    set_offset_callback(update["update_id"] + 1)
                    try:
                        if "message" in update:
                            if not _submit_task_provider()(message_handler_provider(), update["message"]):
                                chat_id = str(update["message"].get("chat", {}).get("id", ""))
                                if chat_id:
                                    _send_provider()(chat_id, "⏳ 当前请求人数过多，请稍后再试...")
                        elif "callback_query" in update:
                            if not _submit_task_provider()(callback_handler_provider(), update["callback_query"]):
                                pass
                    except Exception as e:
                        _logger_provider().error(f"[UserBot] 处理消息异常: {e}")
            else:
                if stop_event.wait(3):
                    return
        except Exception as e:
            _logger_provider().debug(f"[UserBot] polling 异常: {e}")
            if stop_event.wait(5):
                return
