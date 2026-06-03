import logging


logger = logging.getLogger("uvicorn")

_logger_provider = lambda: logger


def _default_get_today_updates():
    from app.domains.notifications.calendar_notify import get_today_updates
    return get_today_updates


def _default_format_notify_message():
    from app.domains.notifications.calendar_notify import format_notify_message
    return format_notify_message


_today_updates_provider = _default_get_today_updates
_format_notify_message_provider = _default_format_notify_message


HELP_MESSAGE = ("🤖 <b>EmbyPulse 智能助理指南</b>\n\n"
                "📊 <b>数据报表指令</b>\n"
                "/stats - 获取今日播放大盘与用户排行\n"
                "/weekly - 获取本周全站数据周报\n"
                "/monthly - 获取本月活跃度月报\n"
                "/yearly - 获取年度全景总结数据\n\n"
                "🎬 <b>媒体库与状态指令</b>\n"
                "/now - 查看当前服务器有谁正在播放\n"
                "/latest - 获取最近新入库的 8 部影视剧\n"
                "/recent - 查看本站最近的 10 条播放历史\n"
                "/search [关键词] - 搜索影视资源并获取直达链接\n"
                "/calendar - 查看今日剧集更新\n\n"
                "🛠 <b>系统管理指令</b>\n"
                "/check - 测试 Emby 服务器连通性与测速探针\n"
                "/emby_restart - 重启 Emby 服务器（Pro）\n"
                "/whois [TG用户名/TG ID/Emby用户名] - 查询绑定信息与到期时间\n"
                "/help - 获取本帮助菜单")


def set_dependency_providers(
    *,
    today_updates_provider=None,
    format_notify_message_provider=None,
    logger_provider=None,
):
    global _today_updates_provider
    global _format_notify_message_provider
    global _logger_provider

    if today_updates_provider is not None:
        _today_updates_provider = today_updates_provider
    if format_notify_message_provider is not None:
        _format_notify_message_provider = format_notify_message_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def cmd_calendar(bot, cid, platform):
    try:
        updates = _today_updates_provider()()
        message = _format_notify_message_provider()(updates)
        bot.send_message(cid, message, platform=platform)
    except Exception as e:
        _logger_provider().error(f"[Bot] calendar error: {e}")
        bot.send_message(cid, "❌ 获取今日更新失败", platform=platform)


def cmd_help(bot, cid, platform):
    bot.send_message(cid, HELP_MESSAGE.strip(), platform=platform)
