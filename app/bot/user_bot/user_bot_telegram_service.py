from app.infra.clients.telegram_client import telegram_client
from app.infra.config.user_bot_settings import get_user_bot_token
from app.utils.proxy_helper import get_safe_proxies


_telegram_client_provider = lambda: telegram_client
_get_token_provider = lambda: get_user_bot_token
_get_safe_proxies_provider = lambda: get_safe_proxies
_tg_api_provider = lambda: tg_api
_send_provider = lambda: send
_edit_provider = lambda: edit


def set_dependency_providers(
    *,
    telegram_client_provider=None,
    get_token_provider=None,
    get_safe_proxies_provider=None,
    tg_api_provider=None,
    send_provider=None,
    edit_provider=None,
):
    global _telegram_client_provider
    global _get_token_provider
    global _get_safe_proxies_provider
    global _tg_api_provider
    global _send_provider
    global _edit_provider

    if telegram_client_provider is not None:
        _telegram_client_provider = telegram_client_provider
    if get_token_provider is not None:
        _get_token_provider = get_token_provider
    if get_safe_proxies_provider is not None:
        _get_safe_proxies_provider = get_safe_proxies_provider
    if tg_api_provider is not None:
        _tg_api_provider = tg_api_provider
    if send_provider is not None:
        _send_provider = send_provider
    if edit_provider is not None:
        _edit_provider = edit_provider


def tg_api(method, data=None, token=None):
    tk = token or _get_token_provider()()
    if not tk:
        return None
    try:
        response = _telegram_client_provider().post_api(
            tk,
            method,
            json=data,
            proxies=_get_safe_proxies_provider()(),
            timeout=8,
        )
        return response.json() if response.status_code == 200 else None
    except Exception:
        return None


def send(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = reply_markup
    return _tg_api_provider()("sendMessage", data)


def edit(chat_id, message_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = reply_markup
    result = _tg_api_provider()("editMessageText", data)
    if not result or not result.get("ok"):
        return _send_provider()(chat_id, text, reply_markup)
    return result


def reply(chat_id, text, reply_markup=None, msg_id=None):
    if msg_id:
        return _edit_provider()(chat_id, msg_id, text, reply_markup)
    return _send_provider()(chat_id, text, reply_markup)
