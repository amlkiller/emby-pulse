import datetime
import logging
import time

from app.domains.points import point_dao


logger = logging.getLogger("uvicorn")

_get_binding_provider = lambda: (lambda tg_user_id: None)
_tg_api_provider = lambda: (lambda method, data: None)
_edit_provider = lambda: (lambda chat_id, msg_id, text, reply_markup=None: None)
_send_provider = lambda: (lambda chat_id, text, reply_markup=None: None)
_point_dao_provider = lambda: point_dao
_datetime_provider = lambda: datetime
_sleep_provider = lambda: time.sleep
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    get_binding_provider=None,
    tg_api_provider=None,
    edit_provider=None,
    send_provider=None,
    point_dao_provider=None,
    datetime_provider=None,
    sleep_provider=None,
    logger_provider=None,
):
    global _get_binding_provider
    global _tg_api_provider
    global _edit_provider
    global _send_provider
    global _point_dao_provider
    global _datetime_provider
    global _sleep_provider
    global _logger_provider

    if get_binding_provider is not None:
        _get_binding_provider = get_binding_provider
    if tg_api_provider is not None:
        _tg_api_provider = tg_api_provider
    if edit_provider is not None:
        _edit_provider = edit_provider
    if send_provider is not None:
        _send_provider = send_provider
    if point_dao_provider is not None:
        _point_dao_provider = point_dao_provider
    if datetime_provider is not None:
        _datetime_provider = datetime_provider
    if sleep_provider is not None:
        _sleep_provider = sleep_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def _delete_message(chat_id, message_id):
    _tg_api_provider()("deleteMessage", {"chat_id": chat_id, "message_id": message_id})


def _dice_value(response):
    if response and response.get("ok"):
        return response.get("result", {}).get("dice", {}).get("value", 1)
    return 1


def _message_id(response):
    if response and response.get("ok"):
        return response.get("result", {}).get("message_id")
    return None


def _handle_pk_accept_callback(chat_id, tg_user_id, invite_id, cq_id, msg_id):
    """处理PK接受回调"""
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id, "text": "请先绑定账号", "show_alert": True})
        return

    try:
        invite = _point_dao_provider().get_pending_pk_invitation(invite_id)
        if not invite:
            _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id, "text": "邀请不存在或已处理", "show_alert": True})
            _edit_provider()(chat_id, msg_id, "❌ PK邀请已不存在或已处理")
            return

        if invite["target_id"] != binding["emby_user_id"]:
            _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id, "text": "这不是发给你的PK邀请", "show_alert": True})
            return

        try:
            datetime_module = _datetime_provider()
            expires_at = datetime_module.datetime.fromisoformat(invite["expires_at"])
            if datetime_module.datetime.now() > expires_at:
                _point_dao_provider().mark_pk_invitation_expired(invite_id)
                _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id, "text": "PK邀请已过期", "show_alert": True})
                _edit_provider()(chat_id, msg_id, "❌ PK邀请已过期")
                return
        except Exception:
            pass

        challenger_name = invite["challenger_name"]
        challenger_tg_name = invite["challenger_tg_name"] or challenger_name
        target_name = invite["target_name"]
        target_tg_name = invite["target_tg_name"] or target_name
        points = invite["points"]
        invite_msg_id = invite["message_id"]
        command_msg_id = invite["command_message_id"]

        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id, "text": "🎲 掷骰子中..."})
        _edit_provider()(
            chat_id,
            msg_id,
            f"🎲 <b>PK开始！</b>\n\n{challenger_tg_name} vs {target_tg_name}\n💰 下注：{points} 积分\n\n🎲 正在掷骰子...",
        )

        dice1_resp = _tg_api_provider()("sendDice", {"chat_id": chat_id})
        _sleep_provider()(2)
        dice2_resp = _tg_api_provider()("sendDice", {"chat_id": chat_id})
        _sleep_provider()(2)

        dice1_msg_id = _message_id(dice1_resp)
        dice2_msg_id = _message_id(dice2_resp)
        challenger_roll = _dice_value(dice1_resp)
        target_roll = _dice_value(dice2_resp)

        result = _point_dao_provider().accept_pk_invitation(
            invite_id,
            binding["emby_user_id"],
            challenger_roll=challenger_roll,
            target_roll=target_roll,
            cancel_on_insufficient=True,
        )
        if result.get("status") != "success":
            message = result.get("message", "PK处理失败")
            _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id, "text": message, "show_alert": True})
            _edit_provider()(chat_id, msg_id, f"❌ {message}")
            return

        if result.get("tie"):
            _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id, "text": "平局！积分退还"})
            result_msg = f"⚖️ <b>平局！</b>\n\n{challenger_tg_name}({challenger_roll}点) vs {target_tg_name}({target_roll}点)\n\n积分退还，不扣手续费"
            _send_provider()(chat_id, result_msg)
            _sleep_provider()(5)
            _delete_message(chat_id, msg_id)
            return

        winner_name = result.get("winner_name") or ""
        actual_win = result.get("win_amount", 0)
        tax_rate = result.get("tax_rate", 0)

        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id, "text": f"{winner_name}获胜！"})
        result_msg = f"🎲 <b>PK结果</b>\n\n{challenger_tg_name}({challenger_roll}点) vs {target_tg_name}({target_roll}点)\n\n🎉 <b>{winner_name}</b> 获胜！\n💰 获得 <b>{actual_win}</b> 积分（扣{tax_rate}%手续费）"
        result_resp = _send_provider()(chat_id, result_msg)

        _sleep_provider()(5)

        if command_msg_id:
            _delete_message(chat_id, command_msg_id)
        if invite_msg_id:
            _delete_message(chat_id, invite_msg_id)
        if dice1_msg_id:
            _delete_message(chat_id, dice1_msg_id)
        if dice2_msg_id:
            _delete_message(chat_id, dice2_msg_id)
        if result_resp and result_resp.get("ok"):
            result_msg_id = result_resp.get("result", {}).get("message_id")
            _delete_message(chat_id, result_msg_id)

    except Exception as e:
        _logger_provider().error(f"[UserBot] PK接受回调失败: {e}")
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id, "text": "处理失败，请稍后重试", "show_alert": True})


def _handle_pk_reject_callback(chat_id, tg_user_id, invite_id, cq_id, msg_id):
    """处理PK拒绝回调"""
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id, "text": "请先绑定账号", "show_alert": True})
        return

    try:
        invite = _point_dao_provider().get_pending_pk_invitation(invite_id)
        if not invite:
            _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id, "text": "邀请不存在或已处理", "show_alert": True})
            _edit_provider()(chat_id, msg_id, "❌ PK邀请已不存在或已处理")
            return

        if invite["target_id"] != binding["emby_user_id"]:
            _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id, "text": "这不是发给你的PK邀请", "show_alert": True})
            return

        challenger_name = invite["challenger_name"]
        challenger_tg_name = invite["challenger_tg_name"] or challenger_name
        original_chat_id = invite["chat_id"]
        invite_msg_id = invite["message_id"]
        command_msg_id = invite["command_message_id"]

        _point_dao_provider().set_pk_invitation_status(invite_id, "rejected")

        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id, "text": "已拒绝PK邀请"})

        rejecter_tg_name = binding.get("tg_name") or binding["emby_username"]

        _edit_provider()(chat_id, msg_id, f"❌ <b>{rejecter_tg_name}</b> 已拒绝 <b>{challenger_tg_name}</b> 的PK邀请")

        if original_chat_id and str(original_chat_id) != str(chat_id):
            _send_provider()(original_chat_id, f"❌ <b>{rejecter_tg_name}</b> 拒绝了你的PK邀请")

        _sleep_provider()(5)

        if command_msg_id:
            _delete_message(chat_id, command_msg_id)
        if invite_msg_id:
            _delete_message(chat_id, invite_msg_id)
        _delete_message(chat_id, msg_id)

    except Exception as e:
        _logger_provider().error(f"[UserBot] PK拒绝回调失败: {e}")
        _tg_api_provider()("answerCallbackQuery", {"callback_query_id": cq_id, "text": "处理失败，请稍后重试", "show_alert": True})
