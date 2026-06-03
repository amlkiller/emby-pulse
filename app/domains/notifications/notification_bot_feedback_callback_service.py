from app.domains.media_requests import media_request_dao
from app.infra.clients.telegram_client import telegram_client


_media_request_dao_provider = lambda: media_request_dao
_telegram_client_provider = lambda: telegram_client


def set_dependency_providers(*, media_request_dao_provider=None, telegram_client_provider=None):
    global _media_request_dao_provider
    global _telegram_client_provider

    if media_request_dao_provider is not None:
        _media_request_dao_provider = media_request_dao_provider
    if telegram_client_provider is not None:
        _telegram_client_provider = telegram_client_provider


def handle_feedback_callback(data, cq, cid, mid, token, proxies):
    if not data.startswith("feed_"):
        return False

    parts = data.split("_")
    action = parts[1]
    feed_id = int(parts[2])
    status_map = {"fix": 1, "done": 2, "reject": 3}
    status_text = {"fix": "🛠️ 已标记：修复中", "done": "✅ 已标记：修复完成", "reject": "❌ 已标记：暂不处理(忽略)"}

    if action in status_map:
        _media_request_dao_provider().update_feedback_status(feed_id, status_map[action])
        msg_obj = cq["message"]
        operator = cq.get("from", {}).get("first_name", "Admin")
        if "caption" in msg_obj:
            orig_text = msg_obj.get("caption", "资源报错工单")
            new_text = f"{orig_text}\n\n━━━━━━━━━━━━━━\n{status_text[action]}\n(操作人: {operator})"
            try:
                _telegram_client_provider().post_api(
                    token,
                    "editMessageCaption",
                    json={"chat_id": cid, "message_id": mid, "caption": new_text, "reply_markup": {"inline_keyboard": []}},
                    proxies=proxies,
                    timeout=5,
                )
            except Exception:
                pass
        else:
            orig_text = msg_obj.get("text", "资源报错工单")
            new_text = f"{orig_text}\n\n━━━━━━━━━━━━━━\n{status_text[action]}\n(操作人: {operator})"
            try:
                _telegram_client_provider().post_api(
                    token,
                    "editMessageText",
                    json={"chat_id": cid, "message_id": mid, "text": new_text, "reply_markup": {"inline_keyboard": []}},
                    proxies=proxies,
                    timeout=5,
                )
            except Exception:
                pass
    return True
