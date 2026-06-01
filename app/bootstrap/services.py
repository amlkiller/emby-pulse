import asyncio
import logging
import secrets
import threading
import time

from app.core.session import cleanup_expired_sessions
from app.infra.config.bot_settings import get_webhook_token, set_webhook_token
from app.infra.config.user_bot_settings import get_user_bot_token
from app.services.bot_service import bot
from app.services.risk_service import start_risk_monitor
from app.services.user_bot_service import user_bot

from .user_portal import start_user_portal_server


def ensure_webhook_token() -> None:
    weak_tokens = {"embypulse", "emby", "test", "123456", "password", ""}
    if get_webhook_token() in weak_tokens:
        new_token = secrets.token_urlsafe(32)
        set_webhook_token(new_token)
        logging.getLogger("uvicorn").warning("[安全] Webhook Token 已自动生成（原为弱 token），请更新 Emby Webhook 配置")


def audit_proxy_config() -> None:
    try:
        from app.utils.proxy_helper import audit_existing_proxy_config

        audit_existing_proxy_config()
    except Exception as e:
        print(f"⚠️ proxy_helper 启动自检失败（忽略）: {e}")


def start_user_bot_if_configured() -> None:
    try:
        if get_user_bot_token():
            user_bot.start()
    except Exception as e:
        print(f"⚠️ 用户机器人启动异常: {e}")


def start_dashboard_cache_tasks() -> None:
    from app.routers.stats import preload_dashboard_cache, start_dashboard_cache_refresh_loop

    asyncio.create_task(preload_dashboard_cache())
    asyncio.create_task(start_dashboard_cache_refresh_loop())


def start_community_cache_refresh() -> None:
    def _refresh_loop():
        from app.routers.media_request import _refresh_community_cache

        time.sleep(15)
        _refresh_community_cache()
        while True:
            time.sleep(300)
            _refresh_community_cache()

    threading.Thread(target=_refresh_loop, daemon=True).start()


def start_session_cleanup() -> None:
    try:
        deleted = cleanup_expired_sessions()
        if deleted > 0:
            print(f"[Session] 已清理 {deleted} 个过期会话")
    except Exception as e:
        print(f"[Session] 清理失败: {e}")

    def _session_cleanup_loop():
        logger = logging.getLogger("uvicorn")
        while True:
            try:
                deleted = cleanup_expired_sessions()
                if deleted > 0:
                    logger.info(f"[Session] 已清理 {deleted} 个过期会话")
            except Exception as e:
                logger.error(f"[Session] 清理失败: {e}")
            threading.Event().wait(3600)

    threading.Thread(target=_session_cleanup_loop, daemon=True).start()


def print_startup_panel(request_port: int) -> None:
    from app.core.config import PORT

    print("\n" + "=" * 55)
    print("🚀 [系统启动] EmbyPulse 双引擎初始化成功！")
    print("🤖 [消息通知] 机器人模块已就绪")
    print("🔥 [缓存预热] 仪表盘数据正在后台预热...")
    print("🎈 [用户社区] 首页缓存已启用，每 5 分钟自动刷新")
    print("👁️ [风险管控] 并发天眼已开启，时刻监控越界行为！")
    print(f"🌍 [核心后台] 管理员仪表盘运行在端口: {PORT}")
    print(f"🎈 [用户中心] 独立求片门户运行在端口: {request_port}")
    print("✅ [系统状态] 物理隔离架构已启动，安全防护中！")
    if user_bot.running:
        print("🤖 [Pro专属] 用户 TG 机器人已上线！")
    print("=" * 55 + "\n")


def start_bootstrap_services(app, request_port: int) -> None:
    ensure_webhook_token()
    audit_proxy_config()

    bot.start()
    start_user_bot_if_configured()
    threading.Thread(target=start_user_portal_server, args=(app, request_port), daemon=True).start()
    start_risk_monitor()

    start_dashboard_cache_tasks()
    start_community_cache_refresh()
    start_session_cleanup()
    print_startup_panel(request_port)


def stop_bootstrap_services() -> None:
    print("\n" + "=" * 55)
    print("🛑 [系统关闭] 正在停止 EmbyPulse 服务...")
    bot.stop()
    user_bot.stop()
    print("💤 [系统关闭] 所有服务已安全退出。")
    print("=" * 55 + "\n")
