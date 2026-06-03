import datetime
import logging
import re
import secrets

from app.core.security_utils import safe_error_message
from app.domains.users import user_bot_dao
from app.domains.users import user_dao
from app.infra.clients.media_server_client import media_api
from app.infra.config.user_bot_settings import (
    get_user_bot_allow_routes,
    get_user_bot_block_routes,
    get_user_bot_max_reg,
    get_user_bot_reg_days,
    get_user_bot_reg_quota,
    get_user_bot_reg_quota_mode,
    get_user_bot_template_user,
    is_user_bot_open_reg_enabled,
    set_user_bot_open_reg_enabled,
)


logger = logging.getLogger("uvicorn")

_enter_reg_queue_provider = lambda: (lambda chat_id: True)
_leave_reg_queue_provider = lambda: (lambda: None)
_open_reg_enabled_provider = lambda: is_user_bot_open_reg_enabled()
_send_provider = lambda: (lambda chat_id, text, reply_markup=None: None)
_reg_quota_mode_provider = lambda: get_user_bot_reg_quota_mode()
_reg_quota_provider = lambda: get_user_bot_reg_quota()
_reserve_quota_slot_provider = lambda: (lambda quota_mode, quota: (True, None))
_release_quota_slot_provider = lambda: (lambda committed, quota_mode, quota: None)
_set_open_reg_enabled_provider = lambda: set_user_bot_open_reg_enabled
_send_open_reg_closed_notify_provider = lambda: (lambda reason="": None)
_max_reg_provider = lambda: get_user_bot_max_reg()
_user_bot_dao_provider = lambda: user_bot_dao
_user_state_provider = lambda: {}
_secrets_provider = lambda: secrets
_get_username_lock_provider = lambda: (lambda username_lower: _NullLock())
_get_users_list_cached_provider = lambda: (lambda max_age=None: [])
_quota_lock_provider = lambda: _NullLock()
_refresh_user_count_cache_locked_provider = lambda: (lambda force=False, quota=0: None)
_user_count_cache_provider = lambda: {"users": []}
_media_api_provider = lambda: media_api
_template_user_provider = lambda: get_user_bot_template_user()
_datetime_provider = lambda: datetime
_reg_days_provider = lambda: get_user_bot_reg_days()
_allow_routes_provider = lambda: get_user_bot_allow_routes()
_block_routes_provider = lambda: get_user_bot_block_routes()
_user_dao_provider = lambda: user_dao
_bind_user_provider = lambda: (lambda tg_user_id, emby_user_id, emby_username, init_password="", tg_username="", tg_display_name="": None)
_main_menu_keyboard_provider = lambda: (lambda binding=None: None)
_safe_error_message_provider = lambda: safe_error_message
_logger_provider = lambda: logger


class _NullLock:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def set_dependency_providers(
    *,
    enter_reg_queue_provider=None,
    leave_reg_queue_provider=None,
    open_reg_enabled_provider=None,
    send_provider=None,
    reg_quota_mode_provider=None,
    reg_quota_provider=None,
    reserve_quota_slot_provider=None,
    release_quota_slot_provider=None,
    set_open_reg_enabled_provider=None,
    send_open_reg_closed_notify_provider=None,
    max_reg_provider=None,
    user_bot_dao_provider=None,
    user_state_provider=None,
    secrets_provider=None,
    get_username_lock_provider=None,
    get_users_list_cached_provider=None,
    quota_lock_provider=None,
    refresh_user_count_cache_locked_provider=None,
    user_count_cache_provider=None,
    media_api_provider=None,
    template_user_provider=None,
    datetime_provider=None,
    reg_days_provider=None,
    allow_routes_provider=None,
    block_routes_provider=None,
    user_dao_provider=None,
    bind_user_provider=None,
    main_menu_keyboard_provider=None,
    safe_error_message_provider=None,
    logger_provider=None,
):
    global _enter_reg_queue_provider
    global _leave_reg_queue_provider
    global _open_reg_enabled_provider
    global _send_provider
    global _reg_quota_mode_provider
    global _reg_quota_provider
    global _reserve_quota_slot_provider
    global _release_quota_slot_provider
    global _set_open_reg_enabled_provider
    global _send_open_reg_closed_notify_provider
    global _max_reg_provider
    global _user_bot_dao_provider
    global _user_state_provider
    global _secrets_provider
    global _get_username_lock_provider
    global _get_users_list_cached_provider
    global _quota_lock_provider
    global _refresh_user_count_cache_locked_provider
    global _user_count_cache_provider
    global _media_api_provider
    global _template_user_provider
    global _datetime_provider
    global _reg_days_provider
    global _allow_routes_provider
    global _block_routes_provider
    global _user_dao_provider
    global _bind_user_provider
    global _main_menu_keyboard_provider
    global _safe_error_message_provider
    global _logger_provider

    if enter_reg_queue_provider is not None:
        _enter_reg_queue_provider = enter_reg_queue_provider
    if leave_reg_queue_provider is not None:
        _leave_reg_queue_provider = leave_reg_queue_provider
    if open_reg_enabled_provider is not None:
        _open_reg_enabled_provider = open_reg_enabled_provider
    if send_provider is not None:
        _send_provider = send_provider
    if reg_quota_mode_provider is not None:
        _reg_quota_mode_provider = reg_quota_mode_provider
    if reg_quota_provider is not None:
        _reg_quota_provider = reg_quota_provider
    if reserve_quota_slot_provider is not None:
        _reserve_quota_slot_provider = reserve_quota_slot_provider
    if release_quota_slot_provider is not None:
        _release_quota_slot_provider = release_quota_slot_provider
    if set_open_reg_enabled_provider is not None:
        _set_open_reg_enabled_provider = set_open_reg_enabled_provider
    if send_open_reg_closed_notify_provider is not None:
        _send_open_reg_closed_notify_provider = send_open_reg_closed_notify_provider
    if max_reg_provider is not None:
        _max_reg_provider = max_reg_provider
    if user_bot_dao_provider is not None:
        _user_bot_dao_provider = user_bot_dao_provider
    if user_state_provider is not None:
        _user_state_provider = user_state_provider
    if secrets_provider is not None:
        _secrets_provider = secrets_provider
    if get_username_lock_provider is not None:
        _get_username_lock_provider = get_username_lock_provider
    if get_users_list_cached_provider is not None:
        _get_users_list_cached_provider = get_users_list_cached_provider
    if quota_lock_provider is not None:
        _quota_lock_provider = quota_lock_provider
    if refresh_user_count_cache_locked_provider is not None:
        _refresh_user_count_cache_locked_provider = refresh_user_count_cache_locked_provider
    if user_count_cache_provider is not None:
        _user_count_cache_provider = user_count_cache_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if template_user_provider is not None:
        _template_user_provider = template_user_provider
    if datetime_provider is not None:
        _datetime_provider = datetime_provider
    if reg_days_provider is not None:
        _reg_days_provider = reg_days_provider
    if allow_routes_provider is not None:
        _allow_routes_provider = allow_routes_provider
    if block_routes_provider is not None:
        _block_routes_provider = block_routes_provider
    if user_dao_provider is not None:
        _user_dao_provider = user_dao_provider
    if bind_user_provider is not None:
        _bind_user_provider = bind_user_provider
    if main_menu_keyboard_provider is not None:
        _main_menu_keyboard_provider = main_menu_keyboard_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def _send_quota_failure(chat_id, reason):
    if reason == "batch_full":
        _send_provider()(chat_id, "❌ 本次开放注册名额已用完，请联系管理员")
        try:
            _set_open_reg_enabled_provider()(False)
        except Exception:
            pass
        _send_open_reg_closed_notify_provider()("批次名额已满")
    elif reason == "total_full":
        _send_provider()(chat_id, "❌ 用户数量已达上限，开放注册已自动关闭")
        try:
            _set_open_reg_enabled_provider()(False)
        except Exception:
            pass
        _send_open_reg_closed_notify_provider()("用户总数已达上限")
    else:
        _send_provider()(chat_id, "❌ 暂时无法检查注册名额，请稍后重试")


def _validate_username(chat_id, custom_name):
    if len(custom_name) > 16:
        _send_provider()(chat_id, f"❌ 用户名最多 16 个字符，当前 {len(custom_name)} 个字符")
        return None

    safe_name = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fa5_\-.@]", "", custom_name)

    if safe_name != custom_name:
        invalid_chars = set(re.findall(r"[^a-zA-Z0-9\u4e00-\u9fa5_\-.@]", custom_name))
        invalid_str = ", ".join(f"'{c}'" for c in list(invalid_chars)[:5])
        _send_provider()(chat_id, f"❌ 用户名包含不支持的字符: {invalid_str}\n\n只允许字母、数字、中文、下划线(_)、连字符(-)、@ 和 .")
        return None

    if not safe_name:
        _send_provider()(chat_id, "❌ 用户名无效，请使用字母、数字、中文、下划线(_)、连字符(-)、@ 或 .")
        return None

    return safe_name


def do_register(chat_id, tg_user_id, custom_name, tg_username="", tg_display_name=""):
    """执行注册逻辑"""
    if not _enter_reg_queue_provider()(chat_id):
        return

    reserved = False
    committed = False
    quota_mode = "total"
    quota = 0
    try:
        if not _open_reg_enabled_provider():
            _send_provider()(chat_id, "❌ 开放注册已关闭，请联系管理员获取注册码后使用 /code 注册码")
            return

        quota_mode = _reg_quota_mode_provider()
        quota = _reg_quota_provider()

        if quota > 0:
            ok, reason = _reserve_quota_slot_provider()(quota_mode, quota)
            if not ok:
                _send_quota_failure(chat_id, reason)
                return
            reserved = True

        max_reg = _max_reg_provider()
        if max_reg > 0 and quota <= 0:
            try:
                count = _user_bot_dao_provider().count_bindings()
                if count >= max_reg:
                    _send_provider()(chat_id, "❌ 注册名额已满，请联系管理员")
                    return
            except Exception:
                pass

        safe_name = _validate_username(chat_id, custom_name)
        if safe_name is None:
            return

        password = _secrets_provider().token_urlsafe(8)
        username_lock = _get_username_lock_provider()(safe_name.lower())

        with username_lock:
            try:
                users = _get_users_list_cached_provider()() or []
                if any(u.get("Name", "").lower() == safe_name.lower() for u in users):
                    with _quota_lock_provider():
                        _refresh_user_count_cache_locked_provider()(force=True)
                        users = _user_count_cache_provider().get("users") or []
                    if any(u.get("Name", "").lower() == safe_name.lower() for u in users):
                        _send_provider()(chat_id, f"❌ 用户名 <b>{safe_name}</b> 已被占用，请换一个")
                        _user_state_provider()[str(tg_user_id)] = {"action": "register_name"}
                        return

                create_res = _media_api_provider().post("/Users/New", json={"Name": safe_name}, timeout=10)
                if create_res.status_code not in [200, 201]:
                    _send_provider()(chat_id, "❌ 创建账号失败，请稍后重试")
                    return
                new_user = create_res.json()
                uid = new_user.get("Id")
                _media_api_provider().post(f"/Users/{uid}/Password", json={"NewPw": password}, timeout=5)

                template_id = _template_user_provider()
                if template_id:
                    try:
                        tpl = _media_api_provider().get(f"/Users/{template_id}", timeout=5).json()
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

                reg_days = _reg_days_provider()
                expire = (_datetime_provider().date.today() + _datetime_provider().timedelta(days=reg_days)).strftime("%Y-%m-%d")

                allow_routes = _allow_routes_provider()
                block_routes = _block_routes_provider()

                if allow_routes or block_routes:
                    _user_dao_provider().save_user_expire_routes(uid, expire, allow_routes, block_routes)
                else:
                    template_routes = None
                    if template_id:
                        try:
                            template_meta = _user_dao_provider().get_user_routes(template_id)
                            if template_meta and (template_meta.get("allow_routes") or template_meta.get("block_routes")):
                                template_routes = template_meta
                        except Exception:
                            pass

                    if template_routes:
                        _user_dao_provider().save_user_expire_routes(
                            uid,
                            expire,
                            template_routes.get("allow_routes", ""),
                            template_routes.get("block_routes", ""),
                        )
                    else:
                        _user_dao_provider().save_user_expire(uid, expire)

                _bind_user_provider()(
                    tg_user_id,
                    uid,
                    safe_name,
                    init_password=password,
                    tg_username=tg_username or tg_display_name,
                    tg_display_name=tg_display_name or str(tg_user_id),
                )

                try:
                    _user_bot_dao_provider().create_registration_log(tg_user_id, safe_name, uid, "open")
                except Exception as e:
                    _logger_provider().error(f"记录注册日志失败: {e}")

                committed = True

                _send_provider()(
                    chat_id,
                    f"🎉 <b>注册成功！</b>\n\n"
                    f"👤 用户名：<code>{safe_name}</code>\n"
                    f"🔑 密码：<code>{password}</code>\n"
                    f"📅 有效期至：{expire}\n\n"
                    f"💡 密码可在「个人中心」随时查看",
                    reply_markup=_main_menu_keyboard_provider()({"emby_user_id": uid, "emby_username": safe_name}),
                )
            except Exception as e:
                _logger_provider().error(f"[注册] 执行异常: {e}")
                _send_provider()(chat_id, f"❌ 注册异常：{_safe_error_message_provider()(e, '注册操作异常，请稍后重试')}")
    finally:
        if reserved:
            try:
                _release_quota_slot_provider()(committed, quota_mode, quota)
            except Exception:
                _logger_provider().exception("[UserBot] 释放 quota 预占失败")
        _leave_reg_queue_provider()()
