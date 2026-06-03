import logging
import datetime
import re
import secrets

from app.core.security_utils import safe_error_message
from app.domains.system import invitation_dao
from app.infra.clients.media_server_client import media_api


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
_enter_reg_queue_provider = lambda: (lambda chat_id: True)
_leave_reg_queue_provider = lambda: (lambda: None)
_get_username_lock_provider = lambda: (lambda username_lower: _NullLock())
_media_api_provider = lambda: media_api
_restore_invitation_code_provider = lambda: restore_invitation_code
_bind_user_provider = lambda: (lambda tg_user_id, emby_user_id, emby_username, init_password="", tg_username="", tg_display_name="": None)
_secrets_provider = lambda: secrets
_datetime_provider = lambda: datetime
_invalidate_users_cache_provider = lambda: _invalidate_users_cache
_send_registration_notifications_provider = lambda: _send_registration_notifications


class _NullLock:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


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
    enter_reg_queue_provider=None,
    leave_reg_queue_provider=None,
    get_username_lock_provider=None,
    media_api_provider=None,
    restore_invitation_code_provider=None,
    bind_user_provider=None,
    secrets_provider=None,
    datetime_provider=None,
    invalidate_users_cache_provider=None,
    send_registration_notifications_provider=None,
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
    global _enter_reg_queue_provider
    global _leave_reg_queue_provider
    global _get_username_lock_provider
    global _media_api_provider
    global _restore_invitation_code_provider
    global _bind_user_provider
    global _secrets_provider
    global _datetime_provider
    global _invalidate_users_cache_provider
    global _send_registration_notifications_provider

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
    if enter_reg_queue_provider is not None:
        _enter_reg_queue_provider = enter_reg_queue_provider
    if leave_reg_queue_provider is not None:
        _leave_reg_queue_provider = leave_reg_queue_provider
    if get_username_lock_provider is not None:
        _get_username_lock_provider = get_username_lock_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if restore_invitation_code_provider is not None:
        _restore_invitation_code_provider = restore_invitation_code_provider
    if bind_user_provider is not None:
        _bind_user_provider = bind_user_provider
    if secrets_provider is not None:
        _secrets_provider = secrets_provider
    if datetime_provider is not None:
        _datetime_provider = datetime_provider
    if invalidate_users_cache_provider is not None:
        _invalidate_users_cache_provider = invalidate_users_cache_provider
    if send_registration_notifications_provider is not None:
        _send_registration_notifications_provider = send_registration_notifications_provider


def _set_code_input_name_state(tg_user_id, code, days, tpl_id, routes, route_mode):
    _user_state_provider()[str(tg_user_id)] = {
        "action": "code_input_name",
        "code": code,
        "days": days,
        "tpl_id": tpl_id,
        "routes": routes,
        "route_mode": route_mode,
    }


def _invalidate_users_cache():
    try:
        from app.domains.users import public_service as user_service

        user_service.invalidate_emby_users_cache()
    except Exception:
        pass


def _send_registration_notifications(safe_name, days, code, tg_user_id):
    try:
        from app.domains.notifications.bot_service import bot
        from app.infra.db.notification_dao import add_system_notification

        days_display = "永久" if (days == -1 or days == 0 or days >= 36500) else f"{days} 天"
        msg = f"🎟️ <b>新用户注册</b>\n\n👤 {safe_name}\n📅 有效期：{days_display}\n🔗 邀请码：{code}\n📱 注册渠道：TG机器人\n🆔 TG：{tg_user_id}"
        bot.notifier.send_message("sys_notify", msg, platform="all")
        add_system_notification("user", f"新用户注册: {safe_name}", f"TG机器人注册，有效期 {days_display}", "/users_manage")
    except Exception:
        pass


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


def do_code_register(chat_id, tg_user_id, custom_name, code, days, tpl_id, routes=None, route_mode=None, tg_username="", tg_display_name=""):
    """执行注册码激活创建账号逻辑"""
    if not _enter_reg_queue_provider()(chat_id):
        return

    try:
        if len(custom_name) > 16:
            _send_provider()(chat_id, f"❌ 用户名最多 16 个字符，当前 {len(custom_name)} 个字符")
            _set_code_input_name_state(tg_user_id, code, days, tpl_id, routes, route_mode)
            return

        safe_name = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fa5_\-.@]", "", custom_name)

        if safe_name != custom_name:
            invalid_chars = set(re.findall(r"[^a-zA-Z0-9\u4e00-\u9fa5_\-.@]", custom_name))
            invalid_str = ", ".join(f"'{c}'" for c in list(invalid_chars)[:5])
            _send_provider()(chat_id, f"❌ 用户名包含不支持的字符: {invalid_str}\n\n只允许字母、数字、中文、下划线(_)、连字符(-)、@ 和 .")
            _set_code_input_name_state(tg_user_id, code, days, tpl_id, routes, route_mode)
            return

        if not safe_name:
            _send_provider()(chat_id, "❌ 用户名无效，请使用字母、数字、中文、下划线(_)、连字符(-)、@ 或 .")
            _set_code_input_name_state(tg_user_id, code, days, tpl_id, routes, route_mode)
            return

        password = _secrets_provider().token_urlsafe(8)
        username_lock = _get_username_lock_provider()(safe_name.lower())

        with username_lock:
            try:
                users = _media_api_provider().get("/Users", timeout=5).json()
                if any(u["Name"].lower() == safe_name.lower() for u in users):
                    _send_provider()(chat_id, f"❌ 用户名 <b>{safe_name}</b> 已被占用，请换一个")
                    _set_code_input_name_state(tg_user_id, code, days, tpl_id, routes, route_mode)
                    return

                if not _invitation_dao_provider().claim_invitation_usage(code, safe_name):
                    _send_provider()(chat_id, "❌ 注册码已失效或已达到使用上限")
                    return

                create_res = _media_api_provider().post("/Users/New", json={"Name": safe_name}, timeout=10)
                if create_res.status_code not in [200, 201]:
                    _restore_invitation_code_provider()(code)
                    _send_provider()(chat_id, "❌ 创建账号失败")
                    return
                new_user = create_res.json()
                uid = new_user.get("Id")
                _media_api_provider().post(f"/Users/{uid}/Password", json={"NewPw": password}, timeout=5)

                if tpl_id:
                    try:
                        tpl = _media_api_provider().get(f"/Users/{tpl_id}", timeout=5).json()
                        if tpl.get("Policy"):
                            policy = tpl["Policy"]
                            policy["IsAdministrator"] = False
                            policy["IsDisabled"] = False
                            _media_api_provider().post(f"/Users/{uid}/Policy", json=policy, timeout=5)
                    except Exception:
                        pass
                else:
                    try:
                        _media_api_provider().post(f"/Users/{uid}/Policy", json={"IsDisabled": False}, timeout=3)
                    except Exception:
                        pass

                if days == -1 or days == 0 or days >= 36500:
                    expire = None
                else:
                    expire = (_datetime_provider().date.today() + _datetime_provider().timedelta(days=days)).strftime("%Y-%m-%d")

                allow_routes = ""
                block_routes = ""
                if routes:
                    if route_mode == "allow":
                        allow_routes = routes
                    else:
                        block_routes = routes

                _invitation_dao_provider().save_code_registration_meta_and_finish_invitation(
                    code,
                    uid,
                    expire,
                    allow_routes,
                    block_routes,
                )

                _invalidate_users_cache_provider()()
                _bind_user_provider()(
                    tg_user_id,
                    uid,
                    safe_name,
                    init_password=password,
                    tg_username=tg_username or tg_display_name,
                    tg_display_name=tg_display_name or str(tg_user_id),
                )

                if days == -1 or days == 0 or days >= 36500:
                    expire_display = "♾️ 永久有效"
                else:
                    expire_display = f"{days} 天（至 {expire}）"

                _send_provider()(
                    chat_id,
                    f"🎉 <b>注册码激活成功！</b>\n\n👤 用户名：<code>{safe_name}</code>\n🔑 密码：<code>{password}</code>\n📅 有效期：{expire_display}\n\n💡 密码可在「个人中心」随时查看",
                )

                _send_registration_notifications_provider()(safe_name, days, code, tg_user_id)
            except Exception as e:
                _logger_provider().error(f"[注册码] 使用失败: {e}")
                _send_provider()(chat_id, f"❌ 注册码使用失败：{_safe_error_message_provider()(e, '注册操作异常，请稍后重试')}")
    finally:
        _leave_reg_queue_provider()()


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
