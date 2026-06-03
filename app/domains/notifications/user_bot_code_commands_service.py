import logging

from app.core.security_utils import safe_error_message
from app.domains.system import invitation_dao


logger = logging.getLogger("uvicorn")

_clear_restriction_cache_provider = lambda: (lambda tg_user_id: None)
_check_user_restrictions_provider = lambda: (lambda tg_user_id: {"passed": True})
_format_restriction_message_provider = lambda: (lambda check_result: "")
_send_provider = lambda: (lambda chat_id, text, reply_markup=None: None)
_get_binding_provider = lambda: (lambda tg_user_id: None)
_invitation_dao_provider = lambda: invitation_dao
_user_state_provider = lambda: {}
_safe_error_message_provider = lambda: safe_error_message
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    clear_restriction_cache_provider=None,
    check_user_restrictions_provider=None,
    format_restriction_message_provider=None,
    send_provider=None,
    get_binding_provider=None,
    invitation_dao_provider=None,
    user_state_provider=None,
    safe_error_message_provider=None,
    logger_provider=None,
):
    global _clear_restriction_cache_provider
    global _check_user_restrictions_provider
    global _format_restriction_message_provider
    global _send_provider
    global _get_binding_provider
    global _invitation_dao_provider
    global _user_state_provider
    global _safe_error_message_provider
    global _logger_provider

    if clear_restriction_cache_provider is not None:
        _clear_restriction_cache_provider = clear_restriction_cache_provider
    if check_user_restrictions_provider is not None:
        _check_user_restrictions_provider = check_user_restrictions_provider
    if format_restriction_message_provider is not None:
        _format_restriction_message_provider = format_restriction_message_provider
    if send_provider is not None:
        _send_provider = send_provider
    if get_binding_provider is not None:
        _get_binding_provider = get_binding_provider
    if invitation_dao_provider is not None:
        _invitation_dao_provider = invitation_dao_provider
    if user_state_provider is not None:
        _user_state_provider = user_state_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def cmd_check(chat_id, tg_user_id):
    """检查使用限制状态"""
    _clear_restriction_cache_provider()(tg_user_id)

    restriction_check = _check_user_restrictions_provider()(tg_user_id)

    if restriction_check["passed"]:
        _send_provider()(chat_id, "✅ <b>验证通过</b>\n\n你已经满足使用条件，可以正常使用机器人功能。")
    else:
        _send_provider()(chat_id, _format_restriction_message_provider()(restriction_check))


def cmd_code(chat_id, tg_user_id, args):
    if not args:
        _send_provider()(chat_id, "❌ 请输入注册码：/code 你的注册码")
        return
    code = args.strip()
    if _get_binding_provider()(tg_user_id):
        _send_provider()(chat_id, "❌ 你已经绑定了账号，如需续期请使用 /renew 续期码")
        return

    try:
        row = _invitation_dao_provider().get_available_registration_invitation(code)
        if not row:
            _send_provider()(chat_id, "❌ 注册码无效、已被使用或不是注册码")
            return
        days, used, max_uses, tpl_id, routes, route_mode = (
            row["days"],
            row["used_count"],
            row["max_uses"],
            row["template_user_id"],
            row["routes"],
            row["route_mode"],
        )
        if used >= max_uses:
            _send_provider()(chat_id, "❌ 该注册码已达使用上限")
            return

        _user_state_provider()[str(tg_user_id)] = {
            "action": "code_input_name",
            "code": code,
            "days": days,
            "tpl_id": tpl_id,
            "routes": routes,
            "route_mode": route_mode,
        }
        _send_provider()(
            chat_id,
            "🎟️ <b>注册码验证成功！</b>\n\n请输入你想要的用户名（支持字母、数字、中文、下划线(_)、连字符(-)、@、.）：",
            reply_markup={"inline_keyboard": [[{"text": "❌ 取消", "callback_data": "ub_cancel_state"}]]},
        )
        return
    except Exception as e:
        _logger_provider().error(f"[注册码] 验证失败: {e}")
        _send_provider()(chat_id, f"❌ 注册码验证失败：{_safe_error_message_provider()(e, '注册码验证异常，请稍后重试')}")
        return


def restore_invitation_code(code):
    """Emby 用户创建失败时回滚邀请码消费计数"""
    try:
        _invitation_dao_provider().restore_invitation_code_usage(code)
    except Exception:
        pass


def cmd_renew(chat_id, tg_user_id, args):
    if not args:
        _send_provider()(chat_id, "❌ 请输入续期码：/renew 你的续期码")
        return
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        _send_provider()(chat_id, "❌ 请先绑定账号：/bind 用户名")
        return
    code = args.strip()
    try:
        renew_result, renew_error = _invitation_dao_provider().renew_user_with_invitation_code(
            code,
            binding["emby_username"],
            binding["emby_user_id"],
        )
        if renew_error == "invalid":
            _send_provider()(chat_id, "❌ 续期码无效、已被使用、不是续期码或已达使用上限")
            return
        if renew_error == "permanent":
            _send_provider()(chat_id, "❌ 您的账号为永久有效，无需续费！")
            return

        days = renew_result["days"]
        new_exp = renew_result["new_exp"]
        if days == -1 or days == 0 or days >= 36500:
            days_display = "永久"
        else:
            days_display = f"{days} 天"

        _send_provider()(chat_id, f"✅ <b>续期成功！</b>\n\n📅 新到期日：{new_exp}\n⏳ 延长了 {days_display}")
    except Exception as e:
        _logger_provider().error(f"[续期] 执行失败: {e}")
        _send_provider()(chat_id, f"❌ 续期失败：{_safe_error_message_provider()(e, '续期操作异常，请联系管理员')}")
