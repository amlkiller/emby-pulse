from app.domains.notifications import notification_bot_emby_restart_command_service
from app.domains.notifications import notification_bot_feedback_callback_service
from app.domains.notifications import notification_bot_message_center_callback_service
from app.domains.notifications import notification_bot_plugin_callback_service
from app.domains.notifications import notification_bot_request_approval_action_callback_service
from app.domains.notifications import notification_bot_request_approval_menu_callback_service
from app.domains.notifications import notification_bot_request_hdhive_search_callback_service
from app.domains.notifications import notification_bot_risk_ban_callback_service
from app.infra.clients.telegram_client import telegram_client
from app.infra.config.notification_settings import get_tg_bot_token as get_notify_tg_bot_token
from app.utils.proxy_helper import get_safe_proxies


_notify_tg_bot_token_provider = lambda: get_notify_tg_bot_token()
_safe_proxies_provider = lambda: get_safe_proxies()
_telegram_client_provider = lambda: telegram_client
_plugin_callback_service_provider = lambda: notification_bot_plugin_callback_service
_emby_restart_command_service_provider = lambda: notification_bot_emby_restart_command_service
_message_center_callback_service_provider = lambda: notification_bot_message_center_callback_service
_risk_ban_callback_service_provider = lambda: notification_bot_risk_ban_callback_service
_feedback_callback_service_provider = lambda: notification_bot_feedback_callback_service
_request_hdhive_search_callback_service_provider = lambda: notification_bot_request_hdhive_search_callback_service
_request_approval_menu_callback_service_provider = lambda: notification_bot_request_approval_menu_callback_service
_request_approval_action_callback_service_provider = lambda: notification_bot_request_approval_action_callback_service


def set_dependency_providers(
    *,
    notify_tg_bot_token_provider=None,
    safe_proxies_provider=None,
    telegram_client_provider=None,
    plugin_callback_service_provider=None,
    emby_restart_command_service_provider=None,
    message_center_callback_service_provider=None,
    risk_ban_callback_service_provider=None,
    feedback_callback_service_provider=None,
    request_hdhive_search_callback_service_provider=None,
    request_approval_menu_callback_service_provider=None,
    request_approval_action_callback_service_provider=None,
):
    global _notify_tg_bot_token_provider
    global _safe_proxies_provider
    global _telegram_client_provider
    global _plugin_callback_service_provider
    global _emby_restart_command_service_provider
    global _message_center_callback_service_provider
    global _risk_ban_callback_service_provider
    global _feedback_callback_service_provider
    global _request_hdhive_search_callback_service_provider
    global _request_approval_menu_callback_service_provider
    global _request_approval_action_callback_service_provider

    if notify_tg_bot_token_provider is not None:
        _notify_tg_bot_token_provider = notify_tg_bot_token_provider
    if safe_proxies_provider is not None:
        _safe_proxies_provider = safe_proxies_provider
    if telegram_client_provider is not None:
        _telegram_client_provider = telegram_client_provider
    if plugin_callback_service_provider is not None:
        _plugin_callback_service_provider = plugin_callback_service_provider
    if emby_restart_command_service_provider is not None:
        _emby_restart_command_service_provider = emby_restart_command_service_provider
    if message_center_callback_service_provider is not None:
        _message_center_callback_service_provider = message_center_callback_service_provider
    if risk_ban_callback_service_provider is not None:
        _risk_ban_callback_service_provider = risk_ban_callback_service_provider
    if feedback_callback_service_provider is not None:
        _feedback_callback_service_provider = feedback_callback_service_provider
    if request_hdhive_search_callback_service_provider is not None:
        _request_hdhive_search_callback_service_provider = request_hdhive_search_callback_service_provider
    if request_approval_menu_callback_service_provider is not None:
        _request_approval_menu_callback_service_provider = request_approval_menu_callback_service_provider
    if request_approval_action_callback_service_provider is not None:
        _request_approval_action_callback_service_provider = request_approval_action_callback_service_provider


def _answer_callback(token, cq_id, proxies, payload=None):
    data = {"callback_query_id": cq_id}
    if payload:
        data.update(payload)
    try:
        _telegram_client_provider().post_api(
            token,
            "answerCallbackQuery",
            json=data,
            proxies=proxies,
            timeout=5,
        )
    except Exception:
        pass


def _is_management_callback(data):
    return data.startswith("req_") or data.startswith("feed_")


def _check_management_permission(bot, data, cq, cid, cq_id, token, proxies):
    if not _is_management_callback(data):
        return True

    user_id = cq.get("from", {}).get("id")
    if bot._check_admin_permission(cid, user_id):
        return True

    _answer_callback(
        token,
        cq_id,
        proxies,
        {"text": "⛔ 您没有权限执行此操作", "show_alert": True},
    )
    return False


def _handle_request_callbacks(data, cq, cid, cq_id, mid, token, proxies):
    if not data.startswith("req_"):
        return False

    if _request_hdhive_search_callback_service_provider().handle_request_hdhive_search_callback(
        data,
        cid,
        cq_id,
        mid,
        token,
        proxies,
    ):
        return True

    if _request_approval_menu_callback_service_provider().handle_request_approval_menu_callback(data, cid, mid, token, proxies):
        return True

    if _request_approval_action_callback_service_provider().handle_request_approval_action_callback(data, cq, cid, mid, token, proxies):
        return True

    return False


def handle_callback(bot, cq):
    data = cq.get("data", "")
    cid = str(cq["message"]["chat"]["id"])
    mid = cq["message"]["message_id"]
    cq_id = cq["id"]
    token = _notify_tg_bot_token_provider()
    proxies = _safe_proxies_provider()

    if not _check_management_permission(bot, data, cq, cid, cq_id, token, proxies):
        return

    _answer_callback(token, cq_id, proxies)

    if _plugin_callback_service_provider().handle_plugin_callback(data, cid, cq_id, cq):
        return

    if data.startswith("emby_restart:"):
        _emby_restart_command_service_provider().handle_emby_restart_callback(
            bot,
            data,
            cid,
            cq,
            platform="tg",
        )
        return

    if _plugin_callback_service_provider().handle_request_hdhive_callback(data, cid, cq_id):
        return

    if _message_center_callback_service_provider().handle_message_center_callback(bot, data, cid, mid, token, proxies, cq):
        return

    if _risk_ban_callback_service_provider().handle_risk_ban_callback(bot, data, cq, cid, mid, token, proxies):
        return

    if _feedback_callback_service_provider().handle_feedback_callback(data, cq, cid, mid, token, proxies):
        return

    _handle_request_callbacks(data, cq, cid, cq_id, mid, token, proxies)
