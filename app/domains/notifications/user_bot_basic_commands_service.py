import logging

from app.core.security_utils import safe_error_message
from app.domains.notifications import user_bot_binding_service
from app.infra.clients.media_server_client import media_api
from app.infra.config.user_bot_settings import is_user_bot_open_reg_enabled


logger = logging.getLogger("uvicorn")

_record_bot_user_provider = lambda: user_bot_binding_service.record_bot_user
_get_binding_provider = lambda: user_bot_binding_service.get_binding
_bind_user_provider = lambda: user_bot_binding_service.bind_user
_is_blacklisted_provider = lambda: user_bot_binding_service.is_blacklisted
_send_provider = lambda: (lambda chat_id, text, reply_markup=None: None)
_main_menu_keyboard_provider = lambda: (lambda binding=None: None)
_media_api_provider = lambda: media_api
_open_reg_enabled_provider = lambda: is_user_bot_open_reg_enabled()
_user_state_provider = lambda: {}
_safe_error_message_provider = lambda: safe_error_message
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    record_bot_user_provider=None,
    get_binding_provider=None,
    bind_user_provider=None,
    is_blacklisted_provider=None,
    send_provider=None,
    main_menu_keyboard_provider=None,
    media_api_provider=None,
    open_reg_enabled_provider=None,
    user_state_provider=None,
    safe_error_message_provider=None,
    logger_provider=None,
):
    global _record_bot_user_provider
    global _get_binding_provider
    global _bind_user_provider
    global _is_blacklisted_provider
    global _send_provider
    global _main_menu_keyboard_provider
    global _media_api_provider
    global _open_reg_enabled_provider
    global _user_state_provider
    global _safe_error_message_provider
    global _logger_provider

    if record_bot_user_provider is not None:
        _record_bot_user_provider = record_bot_user_provider
    if get_binding_provider is not None:
        _get_binding_provider = get_binding_provider
    if bind_user_provider is not None:
        _bind_user_provider = bind_user_provider
    if is_blacklisted_provider is not None:
        _is_blacklisted_provider = is_blacklisted_provider
    if send_provider is not None:
        _send_provider = send_provider
    if main_menu_keyboard_provider is not None:
        _main_menu_keyboard_provider = main_menu_keyboard_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if open_reg_enabled_provider is not None:
        _open_reg_enabled_provider = open_reg_enabled_provider
    if user_state_provider is not None:
        _user_state_provider = user_state_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def cmd_start(chat_id, tg_user_id, tg_name):
    _record_bot_user_provider()(tg_user_id, tg_name)

    binding = _get_binding_provider()(tg_user_id)
    if binding:
        msg = (f"👋 欢迎回来，<b>{binding['emby_username']}</b>！\n\n"
               f"🎬 EmbyPulse 用户自助服务\n"
               f"请选择你需要的服务：")
    else:
        msg = (f"👋 你好 <b>{tg_name}</b>！\n\n"
               f"🎬 这是 <b>EmbyPulse</b> 用户自助服务机器人\n\n"
               f"你还没有绑定账号，请先完成绑定或注册：")
    _send_provider()(chat_id, msg, reply_markup=_main_menu_keyboard_provider()(binding))


def cmd_help(chat_id, tg_user_id):
    binding = _get_binding_provider()(tg_user_id)
    status = f"✅ 已绑定：<b>{binding['emby_username']}</b>" if binding else "❌ 未绑定账号"
    _send_provider()(
        chat_id,
        f"🤖 <b>EmbyPulse 用户助手</b>\n\n{status}\n\n"
        "📋 <b>命令列表</b>\n"
        "/bind 用户名 — 绑定 Emby 账号\n"
        "/register — 开放注册\n"
        "/code 注册码 — 注册码激活\n"
        "/renew 续期码 — 续期码续期\n"
        "/checkin — 每日签到\n"
        "/points — 积分余额\n"
        "/shop — 积分商城\n"
        "/pk 积分 — PK掷骰子\n"
        "/lottery 号码 — 彩票\n"
        "/scratch — 刮刮乐\n"
        "/request 关键词 — 求片\n"
        "/server — 服务器状态\n"
        "/library — 媒体库统计\n"
        "/menu — 返回主菜单",
        reply_markup=_main_menu_keyboard_provider()(binding),
    )


def cmd_bind(chat_id, tg_user_id, args, tg_username="", tg_display_name=""):
    if not args or " " not in args.strip():
        _send_provider()(chat_id, "📝 <b>绑定账号</b>\n\n请发送命令（用户名和密码用空格隔开）：\n<code>/bind 用户名 密码</code>\n\n例如：<code>/bind zhangsan mypassword</code>")
        return
    parts = args.strip().split(" ", 1)
    username = parts[0].strip()
    password = parts[1].strip() if len(parts) > 1 else ""
    if not password:
        _send_provider()(chat_id, "❌ 请同时输入密码：/bind 用户名 密码")
        return
    try:
        res = _media_api_provider().authenticate_by_name(username, password, timeout=10)
        if res.status_code != 200:
            _send_provider()(chat_id, "❌ 用户名或密码错误，请检查后重试")
            return
        user_info = res.json().get("User", {})
        uid = user_info.get("Id")
        uname = user_info.get("Name", username)
        _bind_user_provider()(tg_user_id, uid, uname, tg_username=tg_username, tg_display_name=tg_display_name)
        _send_provider()(
            chat_id,
            f"✅ <b>绑定成功！</b>\n\n👤 Emby 账号：<b>{uname}</b>\n\n发送 /menu 打开主菜单",
            reply_markup=_main_menu_keyboard_provider()({"emby_user_id": uid, "emby_username": uname}),
        )
    except Exception as e:
        _logger_provider().error(f"[绑定] Emby绑定失败: {e}")
        _send_provider()(chat_id, f"❌ 绑定失败：{_safe_error_message_provider()(e, '绑定操作异常，请稍后重试')}")


def cmd_register(chat_id, tg_user_id, tg_name):
    if not _open_reg_enabled_provider():
        _send_provider()(chat_id, "❌ 开放注册未开启，请联系管理员获取注册码后使用 /code 注册码")
        return
    if _get_binding_provider()(tg_user_id):
        _send_provider()(chat_id, "❌ 你已经绑定了账号，无需重复注册")
        return
    if _is_blacklisted_provider()(tg_user_id):
        _send_provider()(chat_id, "🚫 你的账号已被管理员限制注册，如有疑问请联系管理员。\n\n如果你有注册码，可以使用 /code 注册码 进行注册。")
        return
    _user_state_provider()[str(tg_user_id)] = {"action": "register_name"}
    _send_provider()(
        chat_id,
        "🆕 <b>注册新账号</b>\n\n请输入你想要的用户名（支持字母、数字、中文、下划线(_)、连字符(-)、@、.）：",
        reply_markup={"inline_keyboard": [[{"text": "❌ 取消", "callback_data": "ub_cancel_state"}]]},
    )
