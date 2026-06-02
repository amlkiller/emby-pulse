from app.infra.config.bot_settings import ensure_strong_webhook_token
from app.domains.notifications.bot_service import (
    is_user_bot_running,
    start_notification_services,
    stop_notification_services,
)
from app.domains.playback.calendar_service import calendar_service
from app.domains.notifications.calendar_notify import calendar_notify_service, start_calendar_notify_services
from app.domains.notifications.router import start_notifications_router_services
from app.domains.playback.dedupe import init_dedupe_db
from app.domains.risk.risk_service import start_risk_monitor, stop_risk_monitor
from app.domains.media_requests.gaps import start_gap_services, stop_gap_services
from app.domains.media_requests.router import start_media_request_services, stop_community_cache_refresh_loop
from app.domains.system.pro import ensure_pro_schema
from app.domains.system.tasks import start_system_task_services, stop_task_poller
from app.domains.users.auth import start_auth_domain_services, stop_auth_domain_services
from app.domains.users.router import start_user_domain_services
from app.core.audit_logger import init_audit_table
from app.core.session import start_session_services, stop_session_cleanup_loop
from app.plugins import disable_enabled_plugins
from app.utils.proxy_helper import audit_existing_proxy_config

from .service_registry import BootstrapServiceRegistry
from .user_portal import start_user_portal_thread, stop_user_portal_thread

_bootstrap_registry = None


def audit_proxy_config() -> None:
    try:
        audit_existing_proxy_config()
    except Exception as e:
        print(f"⚠️ proxy_helper 启动自检失败（忽略）: {e}")


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


def start_dashboard_cache_tasks() -> None:
    from app.domains.playback.stats import start_dashboard_cache_tasks as playback_start_dashboard_cache_tasks

    playback_start_dashboard_cache_tasks()


def stop_dashboard_cache_tasks() -> None:
    from app.domains.playback.stats import stop_dashboard_cache_tasks as playback_stop_dashboard_cache_tasks

    playback_stop_dashboard_cache_tasks()


def build_bootstrap_registry(app, request_port: int) -> BootstrapServiceRegistry:
    registry = BootstrapServiceRegistry()
    registry.register("webhook-token", ensure_strong_webhook_token)
    registry.register("proxy-audit", audit_proxy_config)
    registry.register("notifications", start_notification_services, stop_notification_services)
    registry.register("user-portal", lambda: start_user_portal_thread(app, request_port), stop_user_portal_thread)
    registry.register("risk-monitor", start_risk_monitor, stop_risk_monitor)
    registry.register("dashboard-cache", start_dashboard_cache_tasks, stop_dashboard_cache_tasks)
    registry.register("media-requests", start_media_request_services, stop_community_cache_refresh_loop)
    registry.register("calendar", calendar_service.start, calendar_service.stop)
    registry.register("notifications-router", start_notifications_router_services)
    registry.register("calendar-notify", start_calendar_notify_services, calendar_notify_service.stop)
    registry.register("dedupe", init_dedupe_db)
    registry.register("gaps", start_gap_services, stop_gap_services)
    registry.register("auth-domain", start_auth_domain_services, stop_auth_domain_services)
    registry.register("user-domain", start_user_domain_services)
    registry.register("pro-domain", ensure_pro_schema)
    registry.register("system-tasks", start_system_task_services, stop_task_poller)
    registry.register("audit", init_audit_table)
    registry.register("session", start_session_services, stop_session_cleanup_loop)
    registry.register("plugin-lifecycle", lambda: None, disable_enabled_plugins)
    registry.register("startup-panel", lambda: print_startup_panel(request_port))
    return registry


def get_bootstrap_registry(app, request_port: int) -> BootstrapServiceRegistry:
    global _bootstrap_registry
    if _bootstrap_registry is None:
        _bootstrap_registry = build_bootstrap_registry(app, request_port)
    return _bootstrap_registry


def reset_bootstrap_registry() -> None:
    global _bootstrap_registry
    _bootstrap_registry = None


def start_bootstrap_services(app, request_port: int) -> None:
    get_bootstrap_registry(app, request_port).start_all()


def stop_bootstrap_services() -> None:
    print("\n" + "=" * 55)
    print("🛑 [系统关闭] 正在停止 EmbyPulse 服务...")
    registry = _bootstrap_registry
    if registry is not None:
        registry.stop_all()
        reset_bootstrap_registry()
    print("💤 [系统关闭] 所有服务已安全退出。")
    print("=" * 55 + "\n")
