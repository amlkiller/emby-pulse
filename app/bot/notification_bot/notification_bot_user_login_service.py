import datetime
import logging
import urllib.parse

from app.infra.config.notification_settings import get_notify_user_login
from app.infra.db.notification_dao import add_system_notification
from app.utils.ip_location import get_location


logger = logging.getLogger("uvicorn")

def _default_get_notify_rule(rule_type):
    from app.domains.notifications.notify_admin import get_notify_rule

    return get_notify_rule(rule_type)


_notify_rule_provider = lambda: _default_get_notify_rule
_notify_user_login_provider = lambda: get_notify_user_login
_location_provider = lambda: get_location
_add_system_notification_provider = lambda: add_system_notification
_datetime_provider = lambda: datetime
_quote_provider = lambda: urllib.parse.quote
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    notify_rule_provider=None,
    notify_user_login_provider=None,
    location_provider=None,
    add_system_notification_provider=None,
    datetime_provider=None,
    quote_provider=None,
    logger_provider=None,
):
    global _notify_rule_provider
    global _notify_user_login_provider
    global _location_provider
    global _add_system_notification_provider
    global _datetime_provider
    global _quote_provider
    global _logger_provider

    if notify_rule_provider is not None:
        _notify_rule_provider = notify_rule_provider
    if notify_user_login_provider is not None:
        _notify_user_login_provider = notify_user_login_provider
    if location_provider is not None:
        _location_provider = location_provider
    if add_system_notification_provider is not None:
        _add_system_notification_provider = add_system_notification_provider
    if datetime_provider is not None:
        _datetime_provider = datetime_provider
    if quote_provider is not None:
        _quote_provider = quote_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def _get_user_login_rule():
    return _notify_rule_provider()("user_login")


def _fallback_avatar_url(user_name):
    return "https://api.dicebear.com/9.x/notionists/png?seed=" + _quote_provider()(user_name)


def handle_user_login(bot, data):
    try:
        rule = _get_user_login_rule()
        if not rule or not rule.get("enabled"):
            return
    except:
        if not _notify_user_login_provider()():
            return

    try:
        user = data.get("User") or {}
        session = data.get("Session") or {}
        user_id = user.get("Id") or data.get("UserId")
        user_name = user.get("Name") or data.get("Title") or data.get("UserName") or "未知账号"

        if bot._is_muted(user_id, "login"):
            _logger_provider().info(f"🔇 [静音规则] 拦截了用户 {user_name} 的登录通知")
            return

        ip = session.get("RemoteEndPoint") or data.get("RemoteEndPoint") or "127.0.0.1"
        loc = _location_provider()(ip)
        client = session.get("Client") or data.get("Client") or data.get("AppName") or "未知设备"
        dev_name = session.get("DeviceName") or data.get("DeviceName") or "未知终端"

        msg = (
            f"🔐 <b>安全预警：账号登录</b>\n\n"
            f"👤 <b>用户：</b>{user_name}\n"
            f"🌐 <b>网络：</b>{ip} ({loc})\n"
            f"📱 <b>设备：</b>{client} ({dev_name})\n"
            f"🕒 <b>时间：</b>{_datetime_provider().datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        try:
            rule = _get_user_login_rule()
            channels = rule.get("channels", []) if rule else []

            if "tg_bot" in channels or "wecom" in channels:
                avatar_io = bot._download_user_image(user_id) if user_id else None
                tg_img = avatar_io or _fallback_avatar_url(user_name)
                platform = (
                    "all"
                    if ("tg_bot" in channels and "wecom" in channels)
                    else ("tg" if "tg_bot" in channels else "wecom")
                )
                bot.send_photo("sys_notify", tg_img, msg, platform=platform, wecom_photo_io=tg_img)

            if "web" in channels:
                _add_system_notification_provider()(
                    "user",
                    f"用户登录: {user_name}",
                    f"{ip} ({loc}) - {client}",
                    "/users_manage",
                )
        except Exception as e:
            _logger_provider().error(f"[用户登录通知] 发送失败: {e}")
            avatar_io = bot._download_user_image(user_id) if user_id else None
            tg_img = avatar_io or _fallback_avatar_url(user_name)
            bot.send_photo("sys_notify", tg_img, msg, platform="all", wecom_photo_io=tg_img)
    except Exception as e:
        _logger_provider().error(f"登录通知组装异常: {e}")
