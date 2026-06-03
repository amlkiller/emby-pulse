from app.infra.clients.telegram_client import telegram_client
from app.infra.config.bot_settings import get_tg_chat_id
from app.infra.config.notification_settings import get_tg_bot_token
from app.utils.proxy_helper import get_safe_proxies


_tg_bot_token_provider = lambda: get_tg_bot_token
_tg_chat_id_provider = lambda: get_tg_chat_id
_safe_proxies_provider = lambda: get_safe_proxies
_telegram_client_provider = lambda: telegram_client
_submit_bot_task_provider = lambda: (lambda fn, *args: False)


def set_dependency_providers(
    *,
    tg_bot_token_provider=None,
    tg_chat_id_provider=None,
    safe_proxies_provider=None,
    telegram_client_provider=None,
    submit_bot_task_provider=None,
):
    global _tg_bot_token_provider
    global _tg_chat_id_provider
    global _safe_proxies_provider
    global _telegram_client_provider
    global _submit_bot_task_provider

    if tg_bot_token_provider is not None:
        _tg_bot_token_provider = tg_bot_token_provider
    if tg_chat_id_provider is not None:
        _tg_chat_id_provider = tg_chat_id_provider
    if safe_proxies_provider is not None:
        _safe_proxies_provider = safe_proxies_provider
    if telegram_client_provider is not None:
        _telegram_client_provider = telegram_client_provider
    if submit_bot_task_provider is not None:
        _submit_bot_task_provider = submit_bot_task_provider


def _parse_admin_chat_ids(raw_chat_ids):
    return [
        chat_id.strip()
        for chat_id in str(raw_chat_ids).replace("，", ",").split(",")
        if chat_id.strip()
    ]


def _append_text_link_urls(message, text):
    for entity in message.get("entities", []) + message.get("caption_entities", []):
        if entity.get("type") == "text_link" and entity.get("url"):
            text += " " + entity["url"]
    return text


def run_polling_loop(bot):
    token = _tg_bot_token_provider()()

    while bot.running and not bot._stop_event.is_set():
        admin_ids = _parse_admin_chat_ids(_tg_chat_id_provider()())

        try:
            res = _telegram_client_provider().get_updates(
                token,
                params={"offset": bot.offset, "timeout": 30},
                proxies=_safe_proxies_provider()(),
                timeout=35,
            )
            if res.status_code == 200:
                for update in res.json().get("result", []):
                    bot.offset = update["update_id"] + 1
                    if "message" in update:
                        message = update["message"]
                        chat_id = str(message["chat"]["id"])
                        chat_type = message["chat"].get("type", "")

                        if chat_type in ["group", "supergroup", "channel"]:
                            continue

                        if not admin_ids or chat_id not in admin_ids:
                            continue

                        text = message.get("text", "") or message.get("caption", "")
                        text = _append_text_link_urls(message, text)
                        bot._handle_message(text, chat_id, platform="tg")
                    elif "callback_query" in update:
                        callback_query = update["callback_query"]
                        chat_id = str(callback_query["message"]["chat"]["id"])
                        if not admin_ids or chat_id not in admin_ids:
                            continue
                        _submit_bot_task_provider()(bot._handle_callback, callback_query)
            else:
                if bot._stop_event.wait(5):
                    return
        except:
            if bot._stop_event.wait(5):
                return
