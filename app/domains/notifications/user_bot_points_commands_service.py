import logging

from app.core.security_utils import safe_error_message
from app.domains.points import point_dao


logger = logging.getLogger("uvicorn")

_get_binding_provider = lambda: (lambda tg_user_id: None)
_check_emby_account_provider = lambda: (lambda binding: True)
_unbind_user_provider = lambda: (lambda tg_user_id: None)
_reply_provider = lambda: (lambda chat_id, text, reply_markup=None, msg_id=None: None)
_send_provider = lambda: (lambda chat_id, text, reply_markup=None: None)
_main_menu_keyboard_provider = lambda: (lambda binding=None: None)
_delete_messages_later_provider = lambda: (lambda chat_id, message_ids, delay_seconds=30: None)
_point_dao_provider = lambda: point_dao
_safe_error_message_provider = lambda: safe_error_message
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    get_binding_provider=None,
    check_emby_account_provider=None,
    unbind_user_provider=None,
    reply_provider=None,
    send_provider=None,
    main_menu_keyboard_provider=None,
    delete_messages_later_provider=None,
    point_dao_provider=None,
    safe_error_message_provider=None,
    logger_provider=None,
):
    global _get_binding_provider
    global _check_emby_account_provider
    global _unbind_user_provider
    global _reply_provider
    global _send_provider
    global _main_menu_keyboard_provider
    global _delete_messages_later_provider
    global _point_dao_provider
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
    if main_menu_keyboard_provider is not None:
        _main_menu_keyboard_provider = main_menu_keyboard_provider
    if delete_messages_later_provider is not None:
        _delete_messages_later_provider = delete_messages_later_provider
    if point_dao_provider is not None:
        _point_dao_provider = point_dao_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def _schedule_group_cleanup(chat_id, reply_result, user_msg_id):
    if reply_result and user_msg_id:
        bot_msg_id = reply_result.get("result", {}).get("message_id")
        if bot_msg_id:
            _delete_messages_later_provider()(chat_id, [bot_msg_id, user_msg_id], 30)


def cmd_checkin(chat_id, tg_user_id, msg_id=None, is_group=False, group_name="", user_msg_id=None):
    """签到功能"""
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        if is_group:
            result = _reply_provider()(chat_id, "❌ 请先私聊机器人绑定账号后再签到", msg_id=msg_id)
            if result and user_msg_id:
                _delete_messages_later_provider()(
                    chat_id,
                    [result.get("result", {}).get("message_id"), user_msg_id],
                    30,
                )
            return
        _reply_provider()(chat_id, "❌ 请先绑定账号", msg_id=msg_id)
        return

    if not _check_emby_account_provider()(binding):
        _unbind_user_provider()(tg_user_id)
        if is_group:
            result = _reply_provider()(chat_id, "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。", msg_id=msg_id)
            if result and user_msg_id:
                _delete_messages_later_provider()(
                    chat_id,
                    [result.get("result", {}).get("message_id"), user_msg_id],
                    30,
                )
        else:
            _reply_provider()(
                chat_id,
                "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。",
                reply_markup=_main_menu_keyboard_provider()(None),
                msg_id=msg_id,
            )
        return

    uid = binding["emby_user_id"]
    uname = binding["emby_username"]
    try:
        checkin_result = _point_dao_provider().perform_user_checkin(uid, uname)
        if checkin_result.get("status") == "error":
            result = _reply_provider()(
                chat_id,
                "😊 今天已经签到过了，明天再来吧！",
                reply_markup={"inline_keyboard": [[{"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]} if not is_group else None,
                msg_id=msg_id,
            )
            if is_group:
                _schedule_group_cleanup(chat_id, result, user_msg_id)
            return

        reward = checkin_result["reward"]
        streak_bonus = checkin_result["streak_bonus"]
        streak_count = checkin_result["streak_count"]
        new_pts = checkin_result["balance"]

        msg_lines = ["🎉 签到成功！", "", f"🎲 获得 <b>{reward}</b> 积分"]
        if streak_bonus > 0:
            msg_lines.append(f"🔥 连续签到 <b>{streak_count}</b> 天，额外奖励 <b>{streak_bonus}</b> 积分")
        msg_lines.append(f"💰 当前余额：<b>{new_pts}</b> 积分")

        if is_group and group_name:
            result = _reply_provider()(
                chat_id,
                f"🎉 <b>{uname}</b> 在 <b>{group_name}</b> 签到成功！\n\n" + "\n".join(msg_lines[1:]),
                msg_id=msg_id,
            )
        else:
            result = _reply_provider()(
                chat_id,
                "\n".join(msg_lines),
                reply_markup={
                    "inline_keyboard": [[
                        {"text": "🏪 去商城逛逛", "callback_data": "ub_menu_shop"},
                        {"text": "🔙 主菜单", "callback_data": "ub_back_menu"},
                    ]]
                } if not is_group else None,
                msg_id=msg_id,
            )

        if is_group:
            _schedule_group_cleanup(chat_id, result, user_msg_id)
    except Exception as e:
        _logger_provider().error(f"[签到] 执行失败: {e}")
        _send_provider()(chat_id, f"❌ 签到失败：{_safe_error_message_provider()(e, '签到操作异常，请稍后重试')}")


def cmd_points(chat_id, tg_user_id, msg_id=None, is_group=False):
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        if is_group:
            return _reply_provider()(chat_id, "❌ 请先私聊机器人绑定账号", msg_id=msg_id)
        return _reply_provider()(chat_id, "❌ 请先绑定账号", msg_id=msg_id)

    if not _check_emby_account_provider()(binding):
        _unbind_user_provider()(tg_user_id)
        if is_group:
            return _reply_provider()(chat_id, "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。", msg_id=msg_id)
        return _reply_provider()(
            chat_id,
            "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。",
            reply_markup=_main_menu_keyboard_provider()(None),
            msg_id=msg_id,
        )

    try:
        pts = _point_dao_provider().get_user_points_balance(binding["emby_user_id"])
        if is_group:
            return _reply_provider()(
                chat_id,
                f"💰 <b>{binding['emby_username']}</b> 的积分余额：<b>{pts}</b>",
                msg_id=msg_id,
            )
        return _reply_provider()(
            chat_id,
            f"💰 <b>{binding['emby_username']}</b> 的积分余额\n\n🪙 当前积分：<b>{pts}</b>",
            reply_markup={
                "inline_keyboard": [[
                    {"text": "✅ 签到", "callback_data": "ub_menu_checkin"},
                    {"text": "🏪 商城", "callback_data": "ub_menu_shop"},
                    {"text": "🔙 主菜单", "callback_data": "ub_back_menu"},
                ]]
            },
            msg_id=msg_id,
        )
    except Exception:
        return _reply_provider()(chat_id, "❌ 查询失败", msg_id=msg_id)
