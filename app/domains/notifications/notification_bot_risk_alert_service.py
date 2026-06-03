import logging

from app.infra.config.media_server_settings import get_media_server_main_public_or_host
from app.infra.config.notification_settings import get_pulse_url
from app.infra.db.notification_dao import add_system_notification


logger = logging.getLogger("uvicorn")

_pulse_url_provider = lambda: get_pulse_url
_media_server_main_public_or_host_provider = lambda: get_media_server_main_public_or_host
_add_system_notification_provider = lambda: add_system_notification
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    pulse_url_provider=None,
    media_server_main_public_or_host_provider=None,
    add_system_notification_provider=None,
    logger_provider=None,
):
    global _pulse_url_provider
    global _media_server_main_public_or_host_provider
    global _add_system_notification_provider
    global _logger_provider

    if pulse_url_provider is not None:
        _pulse_url_provider = pulse_url_provider
    if media_server_main_public_or_host_provider is not None:
        _media_server_main_public_or_host_provider = media_server_main_public_or_host_provider
    if add_system_notification_provider is not None:
        _add_system_notification_provider = add_system_notification_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def handle_risk_alert(bot, data):
    uid = data.get("user_id", "")
    username = data.get("username", "未知")
    current = data.get("current", 0)
    limit = data.get("limit", 0)
    devices_info = data.get("devices_info", "未知设备")
    violation_action = data.get("violation_action", "warn_only")

    action_text = {
        "warn_only": "🔔 仅提醒管理员",
        "warn_user": "📢 已警告用户",
        "auto_ban": "🚫 已自动封禁",
    }.get(violation_action, "🔔 仅提醒管理员")

    msg = (
        f"🚨 <b>【风控预警】 账号并发越界</b>\n\n"
        f"👤 <b>涉事用户：</b>{username}\n"
        f"📈 <b>当前并发：</b>{current} / 额度 {limit}\n"
        f"📱 <b>违规设备：</b>\n{devices_info}\n"
        f"⚙️ <b>处理方式：</b>{action_text}\n\n"
        f"⚠️ <i>天眼系统已记录，请立即进行处置！</i>"
    )

    keyboard = {"inline_keyboard": []}
    if uid and violation_action != "auto_ban":
        keyboard["inline_keyboard"].append(
            [{"text": "🚫 立即封禁此违规账号", "callback_data": f"risk_ban_{uid}"}]
        )

    admin_url = _pulse_url_provider()() or _media_server_main_public_or_host_provider()()
    if admin_url:
        risk_url = f"{admin_url.rstrip('/')}/risk"
        keyboard["inline_keyboard"].append([{"text": "🛡️ 前往风控大盘拔网线", "url": risk_url}])

    bot.send_message(
        "sys_notify",
        msg,
        reply_markup=keyboard if keyboard["inline_keyboard"] else None,
        platform="all",
    )

    try:
        _add_system_notification_provider()(
            notify_type="risk",
            title=f"🚨 并发越界: {username}",
            message=f"当前并发 {current} / 额度 {limit}，处理: {action_text}",
            action_url="/risk",
        )
    except Exception as e:
        _logger_provider().error(f"写入风控通知失败: {e}")
