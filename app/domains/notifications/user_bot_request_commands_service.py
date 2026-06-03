import logging

from app.core.security_utils import safe_error_message
from app.domains.media_requests import media_request_dao
from app.infra.clients.tmdb_client import tmdb_client
from app.infra.config.media_server_settings import get_media_server_main_public_url
from app.infra.config.user_bot_settings import get_user_bot_portal_url
from app.utils.proxy_helper import get_safe_proxies


logger = logging.getLogger("uvicorn")

_get_binding_provider = lambda: (lambda tg_user_id: None)
_check_emby_account_provider = lambda: (lambda binding: True)
_unbind_user_provider = lambda: (lambda tg_user_id: None)
_reply_provider = lambda: (lambda chat_id, text, reply_markup=None, msg_id=None: None)
_send_provider = lambda: (lambda chat_id, text, reply_markup=None: None)
_tg_api_provider = lambda: (lambda method, data=None: None)
_main_menu_keyboard_provider = lambda: (lambda binding=None: None)
_tmdb_client_provider = lambda: tmdb_client
_get_safe_proxies_provider = lambda: get_safe_proxies
_media_request_dao_provider = lambda: media_request_dao
_submit_request_provider = lambda: _submit_request
_portal_url_provider = lambda: get_user_bot_portal_url
_media_server_main_public_url_provider = lambda: get_media_server_main_public_url
_request_notification_sender_provider = lambda: _send_request_notification
_safe_error_message_provider = lambda: safe_error_message
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    get_binding_provider=None,
    check_emby_account_provider=None,
    unbind_user_provider=None,
    reply_provider=None,
    send_provider=None,
    tg_api_provider=None,
    main_menu_keyboard_provider=None,
    tmdb_client_provider=None,
    get_safe_proxies_provider=None,
    media_request_dao_provider=None,
    submit_request_provider=None,
    portal_url_provider=None,
    media_server_main_public_url_provider=None,
    request_notification_sender_provider=None,
    safe_error_message_provider=None,
    logger_provider=None,
):
    global _get_binding_provider
    global _check_emby_account_provider
    global _unbind_user_provider
    global _reply_provider
    global _send_provider
    global _tg_api_provider
    global _main_menu_keyboard_provider
    global _tmdb_client_provider
    global _get_safe_proxies_provider
    global _media_request_dao_provider
    global _submit_request_provider
    global _portal_url_provider
    global _media_server_main_public_url_provider
    global _request_notification_sender_provider
    global _safe_error_message_provider
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
    if tg_api_provider is not None:
        _tg_api_provider = tg_api_provider
    if main_menu_keyboard_provider is not None:
        _main_menu_keyboard_provider = main_menu_keyboard_provider
    if tmdb_client_provider is not None:
        _tmdb_client_provider = tmdb_client_provider
    if get_safe_proxies_provider is not None:
        _get_safe_proxies_provider = get_safe_proxies_provider
    if media_request_dao_provider is not None:
        _media_request_dao_provider = media_request_dao_provider
    if submit_request_provider is not None:
        _submit_request_provider = submit_request_provider
    if portal_url_provider is not None:
        _portal_url_provider = portal_url_provider
    if media_server_main_public_url_provider is not None:
        _media_server_main_public_url_provider = media_server_main_public_url_provider
    if request_notification_sender_provider is not None:
        _request_notification_sender_provider = request_notification_sender_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def _reply_deleted_binding(chat_id, tg_user_id, *, use_reply=False, msg_id=None):
    _unbind_user_provider()(tg_user_id)
    text = "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。"
    if use_reply:
        _reply_provider()(
            chat_id,
            text,
            reply_markup=_main_menu_keyboard_provider()(None),
            msg_id=msg_id,
        )
        return
    _send_provider()(chat_id, text, reply_markup=_main_menu_keyboard_provider()(None))


def cmd_request(chat_id, tg_user_id, args):
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        _send_provider()(chat_id, "❌ 请先绑定账号：/bind 用户名")
        return

    if not _check_emby_account_provider()(binding):
        _reply_deleted_binding(chat_id, tg_user_id)
        return

    if not args:
        _send_provider()(chat_id, "🔍 请输入要搜索的影视名称：/request 剧名")
        return
    if not _tmdb_client_provider().api_key:
        _send_provider()(chat_id, "❌ 服务器未配置 TMDB，求片功能不可用")
        return
    try:
        proxies = _get_safe_proxies_provider()()
        res = _tmdb_client_provider().search_multi(args, proxies=proxies, timeout=10, page=1)
        results = [r for r in res.json().get("results", []) if r.get("media_type") in ["movie", "tv"]][:5]
        if not results:
            _send_provider()(chat_id, f"📭 未找到与 <b>{args}</b> 相关的影视")
            return
        msg = f"🔍 <b>搜索结果：{args}</b>\n\n"
        keyboard = {"inline_keyboard": []}
        for r in results:
            name = r.get("title") or r.get("name", "未知")
            year = (r.get("release_date") or r.get("first_air_date") or "")[:4]
            mtype = "🎬" if r["media_type"] == "movie" else "📺"
            msg += f"{mtype} {name} ({year})\n"
            keyboard["inline_keyboard"].append([{"text": f"{mtype} {name} ({year})", "callback_data": f"ub_req_{r['media_type']}_{r['id']}"}])
        keyboard["inline_keyboard"].append([{"text": "🔙 主菜单", "callback_data": "ub_back_menu"}])
        _send_provider()(chat_id, msg + "\n点击下方按钮提交求片：", reply_markup=keyboard)
    except Exception as e:
        _logger_provider().error(f"[搜索] 执行失败: {e}")
        _send_provider()(chat_id, f"❌ 搜索失败：{_safe_error_message_provider()(e, '搜索异常，请稍后重试')}")


def cmd_request_callback(chat_id, tg_user_id, media_type, tmdb_id, cq_id):
    _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id})
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        _send_provider()(chat_id, "❌ 未绑定账号")
        return

    if media_type == "tv":
        try:
            proxies = _get_safe_proxies_provider()()
            detail = _tmdb_client_provider().get_tv_details(tmdb_id, proxies=proxies, timeout=10).json()
            title = detail.get("name", "未知")
            seasons = detail.get("seasons", [])
            real_seasons = [s for s in seasons if s.get("season_number", 0) > 0]
            if len(real_seasons) <= 1:
                _submit_request_provider()(chat_id, tg_user_id, "tv", tmdb_id, 1)
            else:
                msg = f"📺 <b>{title}</b>\n\n请选择要求片的季数："
                keyboard = {"inline_keyboard": []}
                row = []
                for s in real_seasons:
                    sn = s.get("season_number", 1)
                    row.append({"text": f"第 {sn} 季", "callback_data": f"ub_reqsn_{tmdb_id}_{sn}"})
                    if len(row) == 3:
                        keyboard["inline_keyboard"].append(row)
                        row = []
                if row:
                    keyboard["inline_keyboard"].append(row)
                keyboard["inline_keyboard"].append([{"text": "🔙 返回", "callback_data": "ub_back_menu"}])
                _send_provider()(chat_id, msg, reply_markup=keyboard)
        except Exception as e:
            _logger_provider().error(f"[求片] 获取季数失败: {e}")
            _send_provider()(chat_id, f"❌ 获取季数失败：{_safe_error_message_provider()(e, '获取季数异常，请稍后重试')}")
        return

    _submit_request_provider()(chat_id, tg_user_id, "movie", tmdb_id, 0)


def _send_request_notification(uname, title, year, season_str, tmdb_id, poster_path):
    from app.core.config import REPORT_COVER_URL
    from app.domains.notifications.bot_service import bot
    from app.domains.notifications.notify_admin import get_notify_rule
    from app.infra.db.notification_dao import add_system_notification

    msg = f"🎬 <b>收到新求片心愿</b>\n\n👤 <b>用户：</b>{uname}\n📺 <b>内容：</b>{title} ({year}){season_str}\n📱 <b>来源：</b>TG 用户机器人\n\n请及时前往后台审批处理。"
    admin_url = _portal_url_provider()() or _media_server_main_public_url_provider()() or "http://127.0.0.1:10307"
    keyboard = {"inline_keyboard": [
        [{"text": "🚀 推送 MP", "callback_data": f"req_approve_{tmdb_id}"}, {"text": "✋ 手动接单", "callback_data": f"req_manual_{tmdb_id}"}],
        [{"text": "❌ 拒绝求片", "callback_data": f"req_reject_menu_{tmdb_id}"}, {"text": "💻 网页审批", "url": f"{admin_url.rstrip('/')}/requests_admin"}],
    ]}
    rule = get_notify_rule("request_new")
    if rule and rule.get("enabled"):
        channels = rule.get("channels", [])
        platform = "none"
        if "tg_bot" in channels and "wecom" in channels:
            platform = "all"
        elif "tg_bot" in channels:
            platform = "tg"
        elif "wecom" in channels:
            platform = "wecom"
        if platform != "none":
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else REPORT_COVER_URL
            bot.notifier.send_photo("sys_notify", poster_url, msg, reply_markup=keyboard, platform=platform)
        if "web" in channels:
            add_system_notification("request", f"收到新求片: {title}", f"用户 {uname} 通过TG机器人求片", "/requests_admin")


def _submit_request(chat_id, tg_user_id, media_type, tmdb_id, season):
    """实际提交求片逻辑"""
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        return

    if not _check_emby_account_provider()(binding):
        _reply_deleted_binding(chat_id, tg_user_id)
        return

    uid = binding["emby_user_id"]
    uname = binding["emby_username"]
    try:
        proxies = _get_safe_proxies_provider()()
        if media_type == "movie":
            detail = _tmdb_client_provider().get_movie_details(tmdb_id, proxies=proxies, timeout=10).json()
        else:
            detail = _tmdb_client_provider().get_tv_details(tmdb_id, proxies=proxies, timeout=10).json()
        title = detail.get("title") or detail.get("name", "未知")
        year = (detail.get("release_date") or detail.get("first_air_date") or "")[:4]
        poster_path = detail.get("poster_path", "")
        poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""

        submit_result = _media_request_dao_provider().submit_single_media_request(
            uid,
            uname,
            int(tmdb_id),
            media_type,
            title,
            year,
            poster,
            season,
        )
        if not submit_result.get("ok"):
            _send_provider()(chat_id, f"❌ {submit_result.get('message', '求片提交失败')}")
            return

        season_str = f" 第 {season} 季" if media_type == "tv" and season > 0 else ""
        need_cost = submit_result.get("need_cost", False)
        req_cost = submit_result.get("request_cost", 0)
        user_req_free = submit_result.get("user_req_free", 0)
        user_req_free_count = submit_result.get("user_req_free_count", -1)
        if need_cost and req_cost > 0:
            cost_msg = f"\n💰 消耗 {req_cost} 积分"
        elif user_req_free == 1:
            remaining = user_req_free_count - 1 if user_req_free_count > 0 else "无限"
            cost_msg = f"\n🎁 免费求片（剩余 {remaining} 次）" if remaining != "无限" else "\n🎁 免费求片（无限次）"
        else:
            cost_msg = ""
        _send_provider()(
            chat_id,
            f"✅ <b>求片已提交！</b>\n\n🎬 {title} ({year}){season_str}{cost_msg}\n📋 状态：等待管理员审批",
            reply_markup={"inline_keyboard": [[{"text": "📋 我的求片", "callback_data": "ub_menu_myrequests"}, {"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]},
        )

        try:
            _request_notification_sender_provider()(uname, title, year, season_str, tmdb_id, poster_path)
        except Exception as e:
            _logger_provider().error(f"[求片通知] 发送失败: {e}")
    except Exception as e:
        _logger_provider().error(f"[求片] 提交失败: {e}")
        _send_provider()(chat_id, f"❌ 求片提交失败：{_safe_error_message_provider()(e, '求片提交异常，请稍后重试')}")


def cmd_myrequests(chat_id, tg_user_id, msg_id=None):
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        _reply_provider()(chat_id, "❌ 请先绑定账号", msg_id=msg_id)
        return

    if not _check_emby_account_provider()(binding):
        _reply_deleted_binding(chat_id, tg_user_id, use_reply=True, msg_id=msg_id)
        return

    uid = binding["emby_user_id"]
    try:
        rows = _media_request_dao_provider().list_user_recent_requests(uid)
        if not rows:
            _reply_provider()(
                chat_id,
                "📋 <b>我的求片</b>\n\n暂无求片记录",
                reply_markup={"inline_keyboard": [[{"text": "🎬 去求片", "callback_data": "ub_menu_request"}, {"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]},
                msg_id=msg_id,
            )
            return
        status_map = {0: "⏳ 待审批", 1: "📥 下载中", 2: "✅ 已完成", 3: "❌ 已拒绝", 4: "🔧 手动处理中"}
        msg = "📋 <b>我的求片</b>\n\n"
        for r in rows:
            s_str = f" 第{r['season']}季" if r["media_type"] == "tv" and r["season"] > 0 else ""
            icon = "🎬" if r["media_type"] == "movie" else "📺"
            msg += f"{icon} <b>{r['title']}</b> ({r['year']}){s_str}\n   {status_map.get(r['status'], '未知')}\n\n"
        _reply_provider()(
            chat_id,
            msg.strip(),
            reply_markup={"inline_keyboard": [[{"text": "🎬 继续求片", "callback_data": "ub_menu_request"}, {"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]},
            msg_id=msg_id,
        )
    except Exception as e:
        _logger_provider().error(f"[求片] 查询失败: {e}")
        _reply_provider()(chat_id, f"❌ 查询失败：{_safe_error_message_provider()(e, '查询异常，请稍后重试')}", msg_id=msg_id)
