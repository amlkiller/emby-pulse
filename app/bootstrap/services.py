import asyncio
import logging
import secrets
import threading

from app.core.session import start_session_cleanup_loop
from app.infra.config.bot_settings import get_webhook_token, set_webhook_token
from app.domains.notifications.bot_service import (
    is_user_bot_running,
    start_notification_services,
    stop_notification_services,
)
from app.domains.risk.risk_service import start_risk_monitor

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


def start_dashboard_cache_tasks() -> None:
    from app.domains.playback.stats import preload_dashboard_cache, start_dashboard_cache_refresh_loop

    asyncio.create_task(preload_dashboard_cache())
    asyncio.create_task(start_dashboard_cache_refresh_loop())


def start_community_cache_refresh() -> None:
    from app.domains.media_requests.router import start_community_cache_refresh_loop

    start_community_cache_refresh_loop()

def start_session_cleanup() -> None:
    start_session_cleanup_loop()


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
    if is_user_bot_running():
        print("🤖 [Pro专属] 用户 TG 机器人已上线！")
    print("=" * 55 + "\n")


def start_bootstrap_services(app, request_port: int) -> None:
    ensure_webhook_token()
    audit_proxy_config()

    start_notification_services()
    threading.Thread(target=start_user_portal_server, args=(app, request_port), daemon=True).start()
    start_risk_monitor()

    start_dashboard_cache_tasks()
    start_community_cache_refresh()
    start_session_cleanup()
    print_startup_panel(request_port)


def stop_bootstrap_services() -> None:
    print("\n" + "=" * 55)
    print("🛑 [系统关闭] 正在停止 EmbyPulse 服务...")
    stop_notification_services()
    print("💤 [系统关闭] 所有服务已安全退出。")
    print("=" * 55 + "\n")
