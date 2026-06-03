import logging
import time

from app.infra.clients.media_server_client import media_api
from app.infra.clients.network_client import network_client
from app.infra.config.media_server_settings import get_media_server_user_routes


logger = logging.getLogger("uvicorn")

_get_binding_provider = lambda: (lambda tg_user_id: None)
_check_emby_account_provider = lambda: (lambda binding: True)
_unbind_user_provider = lambda: (lambda tg_user_id: None)
_reply_provider = lambda: (lambda chat_id, text, reply_markup=None, msg_id=None: None)
_send_provider = lambda: (lambda chat_id, text, reply_markup=None: None)
_main_menu_keyboard_provider = lambda: (lambda binding=None: None)
_get_media_server_user_routes_provider = lambda: get_media_server_user_routes
_network_client_provider = lambda: network_client
_media_api_provider = lambda: media_api
_calendar_updates_provider = lambda: _get_calendar_functions()[0]
_calendar_formatter_provider = lambda: _get_calendar_functions()[1]
_time_provider = lambda: time
_logger_provider = lambda: logger

_BACK_MENU = {"inline_keyboard": [[{"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]}


def _get_calendar_functions():
    from app.domains.notifications.calendar_notify import get_today_updates, format_notify_message

    return get_today_updates, format_notify_message


def set_dependency_providers(
    *,
    get_binding_provider=None,
    check_emby_account_provider=None,
    unbind_user_provider=None,
    reply_provider=None,
    send_provider=None,
    main_menu_keyboard_provider=None,
    get_media_server_user_routes_provider=None,
    network_client_provider=None,
    media_api_provider=None,
    calendar_updates_provider=None,
    calendar_formatter_provider=None,
    time_provider=None,
    logger_provider=None,
):
    global _get_binding_provider
    global _check_emby_account_provider
    global _unbind_user_provider
    global _reply_provider
    global _send_provider
    global _main_menu_keyboard_provider
    global _get_media_server_user_routes_provider
    global _network_client_provider
    global _media_api_provider
    global _calendar_updates_provider
    global _calendar_formatter_provider
    global _time_provider
    global _logger_provider

    if get_binding_provider is not None:
        _get_binding_provider = get_binding_provider
    if check_emby_account_provider is not None:
        _check_emby_account_provider = check_emby_account_provider
    if unbind_user_provider is not None:
        _unbind_user_provider = unbind_user_provider
    if reply_provider is not None:
        _reply_provider = reply_provider
    if send_provider is not None:
        _send_provider = send_provider
    if main_menu_keyboard_provider is not None:
        _main_menu_keyboard_provider = main_menu_keyboard_provider
    if get_media_server_user_routes_provider is not None:
        _get_media_server_user_routes_provider = get_media_server_user_routes_provider
    if network_client_provider is not None:
        _network_client_provider = network_client_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if calendar_updates_provider is not None:
        _calendar_updates_provider = calendar_updates_provider
    if calendar_formatter_provider is not None:
        _calendar_formatter_provider = calendar_formatter_provider
    if time_provider is not None:
        _time_provider = time_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def _get_valid_binding_or_reply_deleted(chat_id, tg_user_id, msg_id=None):
    binding = _get_binding_provider()(tg_user_id)
    if binding and not _check_emby_account_provider()(binding):
        _unbind_user_provider()(tg_user_id)
        _reply_provider()(
            chat_id,
            "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。",
            reply_markup=_main_menu_keyboard_provider()(None),
            msg_id=msg_id,
        )
        return binding, False
    return binding, True


def cmd_server(chat_id, tg_user_id, msg_id=None):
    binding, is_valid = _get_valid_binding_or_reply_deleted(chat_id, tg_user_id, msg_id=msg_id)
    if not is_valid:
        return

    emby_uid = binding.get("emby_user_id") if binding else None
    try:
        routes = _get_media_server_user_routes_provider()(emby_uid)

        if not routes:
            _send_provider()(chat_id, "📡 管理员未配置公网地址")
            return

        msg = "📡 <b>服务器线路状态</b>\n\n"
        for r in routes:
            name = r.get("name", "未命名")
            url = r.get("url", "").rstrip("/")
            if url:
                try:
                    start = _time_provider().time()
                    _network_client_provider().get(f"{url}/web/favicon.ico", timeout=3)
                    delay = int((_time_provider().time() - start) * 1000)
                    icon = "🟢" if delay < 100 else ("🟡" if delay < 300 else "🔴")
                    msg += f"{icon} <b>{name}</b>：{delay}ms\n🔗 {url}\n\n"
                except Exception:
                    msg += f"🔴 <b>{name}</b>：超时/离线\n🔗 {url}\n\n"
        _reply_provider()(chat_id, msg.strip(), reply_markup=_BACK_MENU, msg_id=msg_id)
    except Exception:
        _reply_provider()(chat_id, "❌ 查询失败", msg_id=msg_id)


def cmd_library(chat_id, tg_user_id, msg_id=None):
    _binding, is_valid = _get_valid_binding_or_reply_deleted(chat_id, tg_user_id, msg_id=msg_id)
    if not is_valid:
        return

    try:
        res = _media_api_provider().get("/Items/Counts", timeout=5)
        if res.status_code == 200:
            d = res.json()
            _reply_provider()(
                chat_id,
                f"📊 <b>媒体库统计</b>\n\n"
                f"🎬 电影：<b>{d.get('MovieCount', 0)}</b> 部\n"
                f"📺 剧集：<b>{d.get('SeriesCount', 0)}</b> 部\n"
                f"🎞️ 总集数：<b>{d.get('EpisodeCount', 0)}</b> 集",
                reply_markup=_BACK_MENU,
                msg_id=msg_id,
            )
        else:
            _send_provider()(chat_id, "❌ 无法获取媒体库信息")
    except Exception:
        _send_provider()(chat_id, "❌ 连接服务器失败")


def cmd_calendar(chat_id, tg_user_id, msg_id=None):
    """今日剧集更新"""
    _binding, is_valid = _get_valid_binding_or_reply_deleted(chat_id, tg_user_id, msg_id=msg_id)
    if not is_valid:
        return

    try:
        updates = _calendar_updates_provider()()
        message = _calendar_formatter_provider()(updates)
        _reply_provider()(chat_id, message, reply_markup=_BACK_MENU, msg_id=msg_id)
    except Exception as e:
        _logger_provider().error(f"[calendar命令] 执行失败: {e}")
        _reply_provider()(chat_id, "❌ 获取今日更新失败，请稍后重试", reply_markup=_BACK_MENU, msg_id=msg_id)
