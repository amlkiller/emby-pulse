import logging

from app.core.security import validate_password_strength
from app.core.security_utils import safe_error_message
from app.domains.users import user_bot_dao
from app.infra.clients.media_server_client import media_api


logger = logging.getLogger("uvicorn")

_get_binding_provider = lambda: (lambda tg_user_id: None)
_check_emby_account_provider = lambda: (lambda binding: True)
_unbind_user_provider = lambda: (lambda tg_user_id: None)
_send_provider = lambda: (lambda chat_id, text, reply_markup=None: None)
_main_menu_keyboard_provider = lambda: (lambda binding=None: None)
_user_state_provider = lambda: {}
_validate_password_strength_provider = lambda: validate_password_strength
_media_api_provider = lambda: media_api
_user_bot_dao_provider = lambda: user_bot_dao
_safe_error_message_provider = lambda: safe_error_message
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    get_binding_provider=None,
    check_emby_account_provider=None,
    unbind_user_provider=None,
    send_provider=None,
    main_menu_keyboard_provider=None,
    user_state_provider=None,
    validate_password_strength_provider=None,
    media_api_provider=None,
    user_bot_dao_provider=None,
    safe_error_message_provider=None,
    logger_provider=None,
):
    global _get_binding_provider
    global _check_emby_account_provider
    global _unbind_user_provider
    global _send_provider
    global _main_menu_keyboard_provider
    global _user_state_provider
    global _validate_password_strength_provider
    global _media_api_provider
    global _user_bot_dao_provider
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
    if main_menu_keyboard_provider is not None:
        _main_menu_keyboard_provider = main_menu_keyboard_provider
    if user_state_provider is not None:
        _user_state_provider = user_state_provider
    if validate_password_strength_provider is not None:
        _validate_password_strength_provider = validate_password_strength_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if user_bot_dao_provider is not None:
        _user_bot_dao_provider = user_bot_dao_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def cmd_password(chat_id, tg_user_id, args):
    """修改密码"""
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

    uname = binding["emby_username"]
    user_state = _user_state_provider()

    state = user_state.get(str(tg_user_id))
    if state and state.get("action") == "change_pwd_step2":
        new_pwd = args.strip() if args else ""
        pw_valid, pw_error = _validate_password_strength_provider()(new_pwd)
        if not pw_valid:
            _send_provider()(chat_id, f"❌ {pw_error}，请重新输入：")
            return
        user_state[str(tg_user_id)] = {"action": "change_pwd_confirm", "new_pwd": new_pwd}
        _send_provider()(
            chat_id,
            "🔐 <b>确认新密码</b>\n\n请再次输入新密码进行确认：",
            reply_markup={"inline_keyboard": [[{"text": "❌ 取消", "callback_data": "ub_cancel_state"}]]},
        )
        return

    if state and state.get("action") == "change_pwd_confirm":
        confirm_pwd = args.strip() if args else ""
        new_pwd = state.get("new_pwd", "")
        if confirm_pwd != new_pwd:
            _send_provider()(
                chat_id,
                "❌ 两次密码不一致，修改失败。",
                reply_markup={"inline_keyboard": [[{"text": "🔙 返回", "callback_data": "ub_back_menu"}]]},
            )
            user_state.pop(str(tg_user_id), None)
            return

        uid = binding["emby_user_id"]
        try:
            res = _media_api_provider().post(f"/Users/{uid}/Password", json={"NewPw": new_pwd}, timeout=5)
            if res.status_code in [200, 204]:
                _send_provider()(
                    chat_id,
                    f"✅ <b>密码修改成功！</b>\n\n新密码：<code>{new_pwd}</code>\n\n请妥善保管你的密码",
                    reply_markup={"inline_keyboard": [[{"text": "🔙 返回", "callback_data": "ub_back_menu"}]]},
                )
            else:
                _send_provider()(chat_id, "❌ 修改密码失败，请稍后重试")
        except Exception as e:
            _logger_provider().error(f"[改密] 执行失败: {e}")
            _send_provider()(chat_id, f"❌ 修改密码失败：{_safe_error_message_provider()(e, '密码修改异常，请稍后重试')}")
        user_state.pop(str(tg_user_id), None)
        return

    if not args or " " not in args.strip():
        _send_provider()(
            chat_id,
            "🔐 <b>修改密码</b>\n\n请发送命令（当前密码和新密码用空格隔开）：\n<code>/password 当前密码 新密码</code>\n\n例如：<code>/password 当前密码 NewPass1</code>\n\n⚠️ 新密码至少 8 位，需包含小写字母 + 大写字母或数字",
            reply_markup={"inline_keyboard": [[{"text": "❌ 取消", "callback_data": "ub_back_menu"}]]},
        )
        return

    parts = args.strip().split(" ", 1)
    old_pwd = parts[0].strip()
    new_pwd = parts[1].strip() if len(parts) > 1 else ""

    pw_valid, pw_error = _validate_password_strength_provider()(new_pwd)
    if not pw_valid:
        _send_provider()(chat_id, f"❌ {pw_error}，请检查后重试")
        return

    uid = binding["emby_user_id"]
    try:
        auth_res = _media_api_provider().authenticate_by_name(uname, old_pwd, timeout=10)
        if auth_res.status_code != 200:
            _send_provider()(chat_id, "❌ 当前密码错误，请检查后重试")
            return

        res = _media_api_provider().post(f"/Users/{uid}/Password", json={"NewPw": new_pwd}, timeout=10)
        if res.status_code in [200, 204]:
            if binding.get("init_password"):
                _user_bot_dao_provider().update_binding_init_password(tg_user_id, new_pwd)

            _send_provider()(
                chat_id,
                f"✅ <b>密码修改成功！</b>\n\n新密码：<code>{new_pwd}</code>\n\n请妥善保管你的密码",
                reply_markup={"inline_keyboard": [[{"text": "🔙 返回", "callback_data": "ub_back_menu"}]]},
            )
        else:
            _send_provider()(chat_id, "❌ 修改密码失败，请稍后重试")
    except Exception as e:
        _logger_provider().error(f"[设密] 执行失败: {e}")
        _send_provider()(chat_id, f"❌ 修改密码失败：{_safe_error_message_provider()(e, '密码修改异常，请稍后重试')}")
