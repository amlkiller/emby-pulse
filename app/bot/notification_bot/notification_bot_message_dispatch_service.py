import logging

from app.core.event_bus import bus
from app.infra.config.bot_settings import get_tg_chat_id


logger = logging.getLogger("uvicorn")

_tg_chat_id_provider = lambda: get_tg_chat_id
_bus_provider = lambda: bus
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    tg_chat_id_provider=None,
    bus_provider=None,
    logger_provider=None,
):
    global _tg_chat_id_provider
    global _bus_provider
    global _logger_provider

    if tg_chat_id_provider is not None:
        _tg_chat_id_provider = tg_chat_id_provider
    if bus_provider is not None:
        _bus_provider = bus_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def is_admin(cid, platform="tg"):
    """检查 chat_id 是否为配置的管理员"""
    if platform == "tg":
        raw_cids = str(_tg_chat_id_provider()())
        admin_ids = [c.strip() for c in raw_cids.replace('，', ',').split(',') if c.strip()]
        return bool(admin_ids and str(cid) in admin_ids)
    elif platform == "wecom":
        # 企业微信通过 touser 配置控制
        return True  # WeCom 消息由 API 直接发送，已受限
    return False


def handle_message(bot, text, cid, platform="tg"):
    text = text.strip()

    # 检查是否在回复模式
    if hasattr(bot, '_msg_reply_mode') and cid in bot._msg_reply_mode:
        bot._handle_msg_reply_message(text, cid)
        return

    # 🔥 注意：更具体的命令要放在前面，避免被短命令匹配
    if text.startswith("/check"):
        bot._cmd_check(cid, platform)
    elif text.startswith("/search"):
        bot._cmd_search(cid, text, platform)
    elif text.startswith("/stats"):
        bot._cmd_stats(cid, 'day', platform)
    elif text.startswith("/weekly"):
        bot._cmd_stats(cid, 'week', platform)
    elif text.startswith("/monthly"):
        bot._cmd_stats(cid, 'month', platform)
    elif text.startswith("/yearly"):
        bot._cmd_stats(cid, 'year', platform)
    elif text.startswith("/now"):
        bot._cmd_now(cid, platform)
    elif text.startswith("/latest"):
        bot._cmd_latest(cid, platform)
    elif text.startswith("/recent"):
        bot._cmd_recent(cid, platform)
    elif text.startswith("/calendar"):
        bot._cmd_calendar(cid, platform)
    elif text.startswith("/emby_restart"):
        bot._cmd_emby_restart(cid, text, platform)
    elif text.startswith("/whois"):
        bot._cmd_whois(cid, text, platform)
    elif text.startswith("/help"):
        bot._cmd_help(cid, platform)
    else:
        # 非命令消息，仅管理员可触发事件总线
        if not bot._is_admin(cid, platform):
            _logger_provider().warning(f"[Bot] 非管理员用户尝试发送非命令消息: {cid}")
            return
        _logger_provider().info(f"[Bot] 非命令消息，发布到事件总线: {text[:50]}...")
        _bus_provider().publish("bot.admin_message", text, cid, platform)
