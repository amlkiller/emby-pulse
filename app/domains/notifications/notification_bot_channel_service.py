import json
import logging

from app.infra.clients.telegram_client import telegram_client
from app.infra.config.notification_settings import get_notify_channels as get_raw_notify_channels
from app.infra.config.notification_settings import get_tg_bot_token
from app.utils.proxy_helper import get_safe_proxies


logger = logging.getLogger("uvicorn")

_notify_channels_provider = lambda: get_raw_notify_channels
_tg_bot_token_provider = lambda: get_tg_bot_token
_safe_proxies_provider = lambda: get_safe_proxies
_telegram_client_provider = lambda: telegram_client
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    notify_channels_provider=None,
    tg_bot_token_provider=None,
    safe_proxies_provider=None,
    telegram_client_provider=None,
    logger_provider=None,
):
    global _notify_channels_provider
    global _tg_bot_token_provider
    global _safe_proxies_provider
    global _telegram_client_provider
    global _logger_provider

    if notify_channels_provider is not None:
        _notify_channels_provider = notify_channels_provider
    if tg_bot_token_provider is not None:
        _tg_bot_token_provider = tg_bot_token_provider
    if safe_proxies_provider is not None:
        _safe_proxies_provider = safe_proxies_provider
    if telegram_client_provider is not None:
        _telegram_client_provider = telegram_client_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def notify_channels(photo_io, caption, keyboard, item_type, item_info):
    """推送入库通知到配置的频道"""
    try:
        notify_channels_str = _notify_channels_provider()()
        if not notify_channels_str:
            return

        notify_channel_rows = json.loads(notify_channels_str)
        if not isinstance(notify_channel_rows, list):
            return

        type_mapping = {
            "movie": "movie",
            "series": "series",
            "season": "series",
            "episode": "episode",
        }
        notify_type = type_mapping.get(item_type.lower(), "")

        for channel in notify_channel_rows:
            if not channel.get("enabled", True):
                continue

            notify_types = channel.get("notify_types", ["movie", "series", "episode"])
            if notify_type and notify_type not in notify_types:
                continue

            chat_id = channel.get("chat_id")
            if not chat_id:
                continue

            channel_name = channel.get("name", chat_id)

            try:
                send_to_channel(chat_id, photo_io, caption, None)
                _logger_provider().info(f"📢 [频道通知] 已推送到频道: {channel_name}")
            except Exception as e:
                _logger_provider().error(f"📢 [频道通知] 推送到频道 {channel_name} 失败: {e}")

    except Exception as e:
        _logger_provider().error(f"📢 [频道通知] 处理频道推送失败: {e}")


def send_to_channel(chat_id, photo_io, caption, keyboard):
    """发送消息到指定频道"""
    token = _tg_bot_token_provider()()
    if not token:
        return

    proxies = _safe_proxies_provider()()

    if photo_io:
        photo_io.seek(0)

    try:
        if photo_io:
            data = {
                "chat_id": chat_id,
                "caption": caption,
                "parse_mode": "HTML",
            }
            if keyboard:
                data["reply_markup"] = json.dumps(keyboard)

            files = {"photo": ("photo.jpg", photo_io, "image/jpeg")}
            res = _telegram_client_provider().send_photo(token, data=data, files=files, proxies=proxies, timeout=30)
        else:
            data = {
                "chat_id": chat_id,
                "text": caption,
                "parse_mode": "HTML",
            }
            if keyboard:
                data["reply_markup"] = json.dumps(keyboard)

            res = _telegram_client_provider().send_message(token, data, proxies=proxies, timeout=30)

        if res.status_code != 200:
            _logger_provider().error(f"📢 [频道通知] 发送失败: {res.text}")

    except Exception as e:
        _logger_provider().error(f"📢 [频道通知] 发送异常: {e}")


def send_to_channels(photo_io, caption, keyboard=None):
    """发送消息到配置的频道（供插件调用）"""
    try:
        notify_channels_str = _notify_channels_provider()()
        if not notify_channels_str:
            _logger_provider().info("📢 [频道通知] 未配置频道，跳过推送")
            return

        notify_channel_rows = json.loads(notify_channels_str)
        if not isinstance(notify_channel_rows, list):
            _logger_provider().warning("📢 [频道通知] 频道配置格式错误")
            return

        enabled_channels = [c for c in notify_channel_rows if c.get("enabled", True)]
        if not enabled_channels:
            _logger_provider().info("📢 [频道通知] 没有启用的频道，跳过推送")
            return

        _logger_provider().info(f"📢 [频道通知] 准备推送到 {len(enabled_channels)} 个频道")

        for channel in enabled_channels:
            chat_id = channel.get("chat_id")
            if not chat_id:
                continue

            channel_name = channel.get("name", chat_id)

            try:
                send_to_channel(chat_id, photo_io, caption, keyboard)
                _logger_provider().info(f"📢 [频道通知] 已推送到频道: {channel_name}")
            except Exception as e:
                _logger_provider().error(f"📢 [频道通知] 推送到频道 {channel_name} 失败: {e}")

    except Exception as e:
        _logger_provider().error(f"📢 [频道通知] 处理频道推送失败: {e}")
