from app.domains.media_requests import media_request_dao
from app.infra.clients.telegram_client import telegram_client
from app.infra.config.notification_settings import get_pulse_url


_media_request_dao_provider = lambda: media_request_dao
_telegram_client_provider = lambda: telegram_client
_pulse_url_provider = lambda: get_pulse_url


def _default_get_plugin(plugin_name):
    from app.plugins import get_plugin

    return get_plugin(plugin_name)


_get_plugin_provider = lambda: _default_get_plugin


def set_dependency_providers(
    *,
    media_request_dao_provider=None,
    telegram_client_provider=None,
    pulse_url_provider=None,
    get_plugin_provider=None,
):
    global _media_request_dao_provider
    global _telegram_client_provider
    global _pulse_url_provider
    global _get_plugin_provider

    if media_request_dao_provider is not None:
        _media_request_dao_provider = media_request_dao_provider
    if telegram_client_provider is not None:
        _telegram_client_provider = telegram_client_provider
    if pulse_url_provider is not None:
        _pulse_url_provider = pulse_url_provider
    if get_plugin_provider is not None:
        _get_plugin_provider = get_plugin_provider


def _edit_reply_markup(cid, mid, keyboard, token, proxies):
    try:
        _telegram_client_provider().post_api(
            token,
            "editMessageReplyMarkup",
            json={"chat_id": cid, "message_id": mid, "reply_markup": keyboard},
            proxies=proxies,
            timeout=5,
        )
    except Exception:
        pass


def _build_reject_menu(tid):
    reasons = ["影片未上映", "剧集未开播", "未找到可用资源", "质量太差等待洗版"]
    return {
        "inline_keyboard": [
            [{"text": reasons[0], "callback_data": f"req_reject_do_{tid}_0"}, {"text": reasons[1], "callback_data": f"req_reject_do_{tid}_1"}],
            [{"text": reasons[2], "callback_data": f"req_reject_do_{tid}_2"}, {"text": reasons[3], "callback_data": f"req_reject_do_{tid}_3"}],
            [{"text": "🔙 取消返回", "callback_data": f"req_back_{tid}"}],
        ]
    }


def _is_hdhive_enabled():
    hdhive_enabled = False
    try:
        hdhive_plugin = _get_plugin_provider()("hdhive")
        hdhive_enabled = hdhive_plugin and hdhive_plugin.enabled
    except Exception:
        pass
    return hdhive_enabled


def _build_back_menu(tid):
    admin_url = _pulse_url_provider()() or "http://127.0.0.1:10307"
    hdhive_enabled = _is_hdhive_enabled()
    r = _media_request_dao_provider().get_request_summary_by_tmdb(tid)
    if hdhive_enabled and r:
        title_safe = r["title"].replace("_", "-").replace(" ", "-")
        return {
            "inline_keyboard": [
                [{"text": "🚀 推送 MP", "callback_data": f"req_approve_{tid}"}, {"text": "✋ 手动接单", "callback_data": f"req_manual_{tid}"}],
                [{"text": "🔍 影巢搜索", "callback_data": f"req_hdhive_{tid}_{r['media_type']}_0_{title_safe}"}, {"text": "❌ 拒绝求片", "callback_data": f"req_reject_menu_{tid}"}],
                [{"text": "💻 网页审批", "url": f"{admin_url}/requests_admin"}],
            ]
        }
    return {
        "inline_keyboard": [
            [{"text": "🚀 推送 MP", "callback_data": f"req_approve_{tid}"}, {"text": "✋ 手动接单", "callback_data": f"req_manual_{tid}"}],
            [{"text": "❌ 拒绝求片", "callback_data": f"req_reject_menu_{tid}"}, {"text": "💻 网页审批", "url": f"{admin_url}/requests_admin"}],
        ]
    }


def handle_request_approval_menu_callback(data, cid, mid, token, proxies):
    if data.startswith("req_reject_menu_"):
        tid = data.replace("req_reject_menu_", "")
        _edit_reply_markup(cid, mid, _build_reject_menu(tid), token, proxies)
        return True

    if data.startswith("req_back_"):
        tid = data.replace("req_back_", "")
        _edit_reply_markup(cid, mid, _build_back_menu(tid), token, proxies)
        return True

    return False
