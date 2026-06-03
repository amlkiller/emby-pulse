import logging

from app.domains.notifications import message_dao
from app.infra.clients.media_server_client import media_api
from app.infra.clients.telegram_client import telegram_client


logger = logging.getLogger("uvicorn")

_message_dao_provider = lambda: message_dao
_telegram_client_provider = lambda: telegram_client
_media_api_provider = lambda: media_api
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    message_dao_provider=None,
    telegram_client_provider=None,
    media_api_provider=None,
    logger_provider=None,
):
    global _message_dao_provider
    global _telegram_client_provider
    global _media_api_provider
    global _logger_provider

    if message_dao_provider is not None:
        _message_dao_provider = message_dao_provider
    if telegram_client_provider is not None:
        _telegram_client_provider = telegram_client_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def handle_msg_reply_callback(bot, cid, mid, user_id, token, proxies):
    """处理回复消息的回调"""
    bot._msg_reply_mode[cid] = user_id

    try:
        row = _message_dao_provider().get_local_user_remark_by_emby_id(user_id)
        user_display = row["remark"] if row and row["remark"] else user_id
    except Exception:
        user_display = user_id

    text = "💬 <b>回复模式</b>\n\n"
    text += f"👤 目标用户：{user_display}\n"
    text += f"🆔 用户ID：<code>{user_id}</code>\n\n"
    text += "📝 请直接发送消息内容，将转发给该用户\n"
    text += "⚠️ 发送任意消息即可回复，或点击下方取消"

    keyboard = {
        "inline_keyboard": [[
            {"text": "❌ 取消回复", "callback_data": f"msg_cancel:{user_id}"}
        ]]
    }

    try:
        _telegram_client_provider().post_api(token, "editMessageText", json={
            "chat_id": cid, "message_id": mid,
            "text": text, "parse_mode": "HTML",
            "reply_markup": keyboard
        }, proxies=proxies, timeout=5)
    except Exception:
        pass


def handle_msg_block_callback(cid, mid, user_id, token, proxies, cq):
    """处理屏蔽通知的回调"""
    try:
        _message_dao_provider().add_notify_block(user_id)

        operator = cq.get('from', {}).get('first_name', 'Admin')
        msg_obj = cq["message"]
        orig_text = msg_obj.get("text", "")
        new_text = f"{orig_text}\n\n━━━━━━━━━━━━━━\n🔇 已屏蔽该用户的消息通知\n(操作人: {operator})"

        keyboard = {
            "inline_keyboard": [[
                {"text": "🔊 取消屏蔽", "callback_data": f"msg_unblock:{user_id}"}
            ]]
        }

        try:
            _telegram_client_provider().post_api(token, "editMessageText", json={
                "chat_id": cid, "message_id": mid,
                "text": new_text, "parse_mode": "HTML",
                "reply_markup": keyboard
            }, proxies=proxies, timeout=5)
        except Exception:
            pass
    except Exception as e:
        _logger_provider().error(f"[Bot] 屏蔽通知失败: {e}")


def handle_msg_unblock_callback(cid, mid, user_id, token, proxies, cq):
    """处理取消屏蔽通知的回调"""
    try:
        _message_dao_provider().remove_notify_block(user_id)

        operator = cq.get('from', {}).get('first_name', 'Admin')
        msg_obj = cq["message"]
        orig_text = msg_obj.get("text", "")
        if "━━━━━━━━━━━━━━" in orig_text:
            orig_text = orig_text.split("━━━━━━━━━━━━━━")[0].strip()

        new_text = f"{orig_text}\n\n━━━━━━━━━━━━━━\n🔊 已取消屏蔽，将恢复消息通知\n(操作人: {operator})"

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "💬 回复消息", "callback_data": f"msg_reply:{user_id}"}
                ],
                [
                    {"text": "🚫 屏蔽通知", "callback_data": f"msg_block:{user_id}"}
                ]
            ]
        }

        try:
            _telegram_client_provider().post_api(token, "editMessageText", json={
                "chat_id": cid, "message_id": mid,
                "text": new_text, "parse_mode": "HTML",
                "reply_markup": keyboard
            }, proxies=proxies, timeout=5)
        except Exception:
            pass
    except Exception as e:
        _logger_provider().error(f"[Bot] 取消屏蔽失败: {e}")


def handle_msg_cancel_callback(bot, cid, mid, token, proxies):
    bot._msg_reply_mode.pop(cid, None)
    try:
        _telegram_client_provider().post_api(token, "editMessageText", json={
            "chat_id": cid, "message_id": mid,
            "text": "❌ 已取消回复",
            "reply_markup": {"inline_keyboard": []}
        }, proxies=proxies, timeout=5)
    except Exception:
        pass


def handle_message_center_callback(bot, data, cid, mid, token, proxies, cq):
    if data.startswith("msg_reply:"):
        user_id = data.replace("msg_reply:", "")
        handle_msg_reply_callback(bot, cid, mid, user_id, token, proxies)
        return True

    if data.startswith("msg_block:"):
        user_id = data.replace("msg_block:", "")
        handle_msg_block_callback(cid, mid, user_id, token, proxies, cq)
        return True

    if data.startswith("msg_cancel:"):
        handle_msg_cancel_callback(bot, cid, mid, token, proxies)
        return True

    if data.startswith("msg_unblock:"):
        user_id = data.replace("msg_unblock:", "")
        handle_msg_unblock_callback(cid, mid, user_id, token, proxies, cq)
        return True

    return False


def handle_msg_reply_message(bot, text, cid):
    """处理回复模式下的消息"""
    if cid not in bot._msg_reply_mode:
        return False

    user_id = bot._msg_reply_mode.pop(cid)

    try:
        conversation = _message_dao_provider().get_conversation_by_user(user_id)
        if not conversation:
            username = user_id
            try:
                api = _media_api_provider()
                if api:
                    user_info = api.get(f"/Users/{user_id}")
                    if user_info and user_info.status_code == 200:
                        username = user_info.json().get("Name", user_id)
            except Exception:
                pass
            conv_id = _message_dao_provider().create_conversation(user_id, username)
        else:
            conv_id = conversation["id"]

        _message_dao_provider().insert_admin_message(conv_id, "bot", "管理员", text, text[:100])

        try:
            from app.domains.notifications.messages import _send_bot_reply_to_user
            _send_bot_reply_to_user(user_id, text, "管理员")
        except Exception:
            pass

        bot.send_message(cid, f"✅ 消息已发送给用户 {user_id}", platform="tg")
        return True

    except Exception as e:
        _logger_provider().error(f"[Bot] 回复消息失败: {e}")
        bot.send_message(cid, f"❌ 发送失败: {e}", platform="tg")
        return True
