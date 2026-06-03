import datetime
import logging

from app.core.security_utils import safe_error_message
from app.domains.playback import stats_queries
from app.domains.users import user_dao
from app.infra.clients.media_server_client import media_api


logger = logging.getLogger("uvicorn")

_get_binding_provider = lambda: (lambda tg_user_id: None)
_check_emby_account_provider = lambda: (lambda binding: True)
_unbind_user_provider = lambda: (lambda tg_user_id: None)
_send_provider = lambda: (lambda chat_id, text, reply_markup=None: None)
_reply_provider = lambda: (lambda chat_id, text, reply_markup=None, msg_id=None: None)
_main_menu_keyboard_provider = lambda: (lambda binding=None: None)
_user_dao_provider = lambda: user_dao
_stats_queries_provider = lambda: stats_queries
_media_api_provider = lambda: media_api
_datetime_provider = lambda: datetime
_safe_error_message_provider = lambda: safe_error_message
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    get_binding_provider=None,
    check_emby_account_provider=None,
    unbind_user_provider=None,
    send_provider=None,
    reply_provider=None,
    main_menu_keyboard_provider=None,
    user_dao_provider=None,
    stats_queries_provider=None,
    media_api_provider=None,
    datetime_provider=None,
    safe_error_message_provider=None,
    logger_provider=None,
):
    global _get_binding_provider
    global _check_emby_account_provider
    global _unbind_user_provider
    global _send_provider
    global _reply_provider
    global _main_menu_keyboard_provider
    global _user_dao_provider
    global _stats_queries_provider
    global _media_api_provider
    global _datetime_provider
    global _safe_error_message_provider
    global _logger_provider

    if get_binding_provider is not None:
        _get_binding_provider = get_binding_provider
    if check_emby_account_provider is not None:
        _check_emby_account_provider = check_emby_account_provider
    if unbind_user_provider is not None:
        _unbind_user_provider = unbind_user_provider
    if send_provider is not None:
        _send_provider = send_provider
    if reply_provider is not None:
        _reply_provider = reply_provider
    if main_menu_keyboard_provider is not None:
        _main_menu_keyboard_provider = main_menu_keyboard_provider
    if user_dao_provider is not None:
        _user_dao_provider = user_dao_provider
    if stats_queries_provider is not None:
        _stats_queries_provider = stats_queries_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if datetime_provider is not None:
        _datetime_provider = datetime_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def cmd_profile(chat_id, tg_user_id, msg_id=None):
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        _send_provider()(chat_id, "❌ 请先绑定账号")
        return

    if not _check_emby_account_provider()(binding):
        _unbind_user_provider()(tg_user_id)
        _send_provider()(
            chat_id,
            "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。",
            reply_markup=_main_menu_keyboard_provider()(None),
        )
        return

    uid = binding["emby_user_id"]
    uname = binding["emby_username"]
    try:
        meta = _user_dao_provider().get_user_points_expire(uid)

        last_play_display = "暂无播放记录"
        try:
            last_play = _stats_queries_provider().get_user_last_play(uid)
            if last_play:
                item_name = last_play.get("ItemName") or last_play[0]
                play_duration = last_play.get("PlayDuration") or last_play[1]
                play_date = last_play.get("DateCreated") or last_play[2]
                minutes = int(play_duration / 60) if play_duration else 0
                play_time = play_date[:16].replace("T", " ") if play_date else "未知"
                last_play_display = f"🎬 {item_name[:20]}{'...' if len(item_name) > 20 else ''}\n   📊 播放 {minutes} 分钟 • {play_time}"
        except Exception as e:
            _logger_provider().warning(f"获取播放记录失败: {e}")
            last_play_display = "暂无播放记录"

        pts = meta["points"] if meta and meta["points"] else 0
        expire = meta["expire_date"] if meta and meta["expire_date"] else "未设置"

        status_str = "正常"
        created_str = "未知"
        try:
            u_res = _media_api_provider().get(f"/Users/{uid}", timeout=5)
            if u_res.status_code == 200:
                u_data = u_res.json()
                if u_data.get("Policy", {}).get("IsDisabled"):
                    status_str = "⛔ 已禁用"
                else:
                    status_str = "✅ 正常"
                dc = u_data.get("DateCreated", "")
                if dc:
                    created_str = dc[:10]
        except Exception:
            pass

        expire_display = expire
        if expire and expire != "未设置":
            try:
                exp_date = _datetime_provider().datetime.strptime(expire, "%Y-%m-%d").date()
                days_left = (exp_date - _datetime_provider().date.today()).days
                if "2099" in expire or "3000" in expire:
                    expire_display = "♾️ 永久有效"
                elif days_left < 0:
                    expire_display = f"❌ 已过期 ({expire})"
                elif days_left <= 7:
                    expire_display = f"⚠️ {expire}（剩余 {days_left} 天）"
                else:
                    expire_display = f"{expire}（剩余 {days_left} 天）"
            except Exception:
                pass

        pwd_display = f"<tg-spoiler>{binding['init_password']}</tg-spoiler>" if binding.get("init_password") else "（手动绑定，未记录）"

        msg = (
            f"👤 <b>个人中心</b>\n\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📛 <b>用户名：</b><code>{uname}</code>\n"
            f"🔑 <b>密码：</b>{pwd_display}\n"
            f"🆔 <b>用户 ID：</b><code>{uid[:8]}...</code>\n"
            f"📅 <b>注册时间：</b>{created_str}\n"
            f"🔰 <b>账号状态：</b>{status_str}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"💰 <b>积分余额：</b>{pts}\n"
            f"⏳ <b>有效期至：</b>{expire_display}\n"
            f"🎬 <b>最后播放：</b>{last_play_display}\n"
            f"━━━━━━━━━━━━━━━━"
        )

        _reply_provider()(
            chat_id,
            msg,
            reply_markup={
                "inline_keyboard": [
                    [
                        {"text": "✅ 签到领积分", "callback_data": "ub_menu_checkin"},
                        {"text": "🎟️ 续期", "callback_data": "ub_menu_renew"},
                    ],
                    [{"text": "🔙 主菜单", "callback_data": "ub_back_menu"}],
                ]
            },
            msg_id=msg_id,
        )
    except Exception as e:
        _logger_provider().error(f"[个人信息] 获取失败: {e}")
        _reply_provider()(
            chat_id,
            f"❌ 获取信息失败：{_safe_error_message_provider()(e, '获取信息异常，请稍后重试')}",
            msg_id=msg_id,
        )


def cmd_unbind(chat_id, tg_user_id):
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        _send_provider()(chat_id, "❌ 你还没有绑定账号")
        return
    _send_provider()(
        chat_id,
        f"🔓 <b>确认解绑？</b>\n\n当前绑定：<b>{binding['emby_username']}</b>\n\n解绑后将无法使用签到、商城等功能。\n\n发送 /unbind_confirm 确认解绑",
    )


def cmd_unbind_confirm(chat_id, tg_user_id):
    _unbind_user_provider()(tg_user_id)
    _send_provider()(chat_id, "✅ 已成功解绑账号。", reply_markup=_main_menu_keyboard_provider()(None))
