import logging

from app.bot.notification_bot import bot_service_dao
from app.infra.clients.telegram_client import telegram_client


logger = logging.getLogger("uvicorn")

_bot_service_dao_provider = lambda: bot_service_dao
_telegram_client_provider = lambda: telegram_client
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    bot_service_dao_provider=None,
    telegram_client_provider=None,
    logger_provider=None,
):
    global _bot_service_dao_provider
    global _telegram_client_provider
    global _logger_provider

    if bot_service_dao_provider is not None:
        _bot_service_dao_provider = bot_service_dao_provider
    if telegram_client_provider is not None:
        _telegram_client_provider = telegram_client_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def ensure_request_admin_messages_table():
    try:
        _bot_service_dao_provider().ensure_request_admin_messages_table()
    except Exception as e:
        _logger_provider().error(f"[求片审核同步] 初始化消息表失败: {e}")


def extract_request_tmdb_id(reply_markup):
    if not reply_markup:
        return None
    for row in reply_markup.get("inline_keyboard", []):
        for button in row:
            data = button.get("callback_data", "")
            if data.startswith("req_approve_") or data.startswith("req_manual_") or data.startswith("req_reject_menu_"):
                parts = data.split("_")
                for part in parts:
                    if part.isdigit():
                        return int(part)
    return None


def record_request_admin_message(tmdb_id, chat_id, message_id, is_caption, original_text):
    if not tmdb_id or not chat_id or not message_id:
        return
    try:
        ensure_request_admin_messages_table()
        _bot_service_dao_provider().save_request_admin_message(tmdb_id, chat_id, message_id, is_caption, original_text)
    except Exception as e:
        _logger_provider().error(f"[求片审核同步] 记录消息失败: {e}")


def sync_request_admin_messages(tmdb_id, action_text, operator, token, proxies, fallback_text="", fallback_is_caption=True):
    if not tmdb_id:
        return
    try:
        ensure_request_admin_messages_table()
        rows = _bot_service_dao_provider().list_request_admin_messages(tmdb_id)

        seen = set()
        for row in rows:
            key = (str(row["chat_id"]), int(row["message_id"]))
            if key in seen:
                continue
            seen.add(key)
            base_text = row["original_text"] or fallback_text or "求片请求"
            new_text = f"{base_text}\n\n━━━━━━━━━━━━━━\n{action_text}\n(操作人: {operator})"
            method = "editMessageCaption" if row["is_caption"] else "editMessageText"
            payload_key = "caption" if row["is_caption"] else "text"
            try:
                payload = {
                    "chat_id": row["chat_id"],
                    "message_id": row["message_id"],
                    payload_key: new_text,
                    "parse_mode": "HTML",
                    "reply_markup": {"inline_keyboard": []},
                }
                _telegram_client_provider().post_api(token, method, json=payload, proxies=proxies, timeout=5)
            except Exception as e:
                _logger_provider().error(f"[求片审核同步] 更新副本失败 chat_id={row['chat_id']} message_id={row['message_id']}: {e}")

        if not rows and fallback_text:
            _logger_provider().info(f"[求片审核同步] 未找到已记录副本 tmdb_id={tmdb_id}")
        elif rows:
            try:
                _bot_service_dao_provider().delete_request_admin_messages(tmdb_id)
            except Exception as e:
                _logger_provider().error(f"[求片审核同步] 清理消息记录失败: {e}")
    except Exception as e:
        _logger_provider().error(f"[求片审核同步] 批量更新失败: {e}")
