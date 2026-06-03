from app.infra.clients.telegram_client import telegram_client
from app.infra.config.notification_settings import get_tg_bot_token
from app.utils.proxy_helper import get_safe_proxies


_tg_bot_token_provider = lambda: get_tg_bot_token
_safe_proxies_provider = lambda: get_safe_proxies
_telegram_client_provider = lambda: telegram_client


BOT_COMMANDS = [
    {"command": "search", "description": "🔍 搜索资源"},
    {"command": "stats", "description": "📊 今日日报"},
    {"command": "weekly", "description": "📅 本周周报"},
    {"command": "monthly", "description": "🗓️ 本月月报"},
    {"command": "yearly", "description": "📜 年度总结"},
    {"command": "now", "description": "🟢 正在播放"},
    {"command": "latest", "description": "🆕 最近入库"},
    {"command": "recent", "description": "📜 最近播放记录"},
    {"command": "check", "description": "📡 系统探针"},
    {"command": "calendar", "description": "📺 今日更新"},
    {"command": "emby_restart", "description": "🔄 重启Emby(Pro)"},
    {"command": "whois", "description": "👤 查询绑定信息"},
    {"command": "help", "description": "🤖 帮助菜单"},
]


def set_dependency_providers(
    *,
    tg_bot_token_provider=None,
    safe_proxies_provider=None,
    telegram_client_provider=None,
):
    global _tg_bot_token_provider
    global _safe_proxies_provider
    global _telegram_client_provider

    if tg_bot_token_provider is not None:
        _tg_bot_token_provider = tg_bot_token_provider
    if safe_proxies_provider is not None:
        _safe_proxies_provider = safe_proxies_provider
    if telegram_client_provider is not None:
        _telegram_client_provider = telegram_client_provider


def set_commands():
    token = _tg_bot_token_provider()()
    if not token:
        return
    try:
        _telegram_client_provider().post_api(
            token,
            "setMyCommands",
            json={"commands": BOT_COMMANDS},
            proxies=_safe_proxies_provider()(),
            timeout=10,
        )
    except Exception:
        pass
