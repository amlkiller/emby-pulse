import ast
import os
import sys
from pathlib import Path

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

_REPO_ROOT = Path(_repo_root)


def test_registry_starts_once_and_stops_in_reverse_order():
    from app.bootstrap.service_registry import BootstrapServiceRegistry

    events = []
    registry = BootstrapServiceRegistry()
    registry.register("first", lambda: events.append("start:first"), lambda: events.append("stop:first"))
    registry.register("second", lambda: events.append("start:second"), lambda: events.append("stop:second"))

    registry.start_all()
    registry.start_all()

    assert events == ["start:first", "start:second"]
    assert registry.started_names() == ["first", "second"]

    registry.stop_all()

    assert events == ["start:first", "start:second", "stop:second", "stop:first"]
    assert registry.started_names() == []


def test_registry_clears_started_state_when_stop_callback_raises():
    from app.bootstrap.service_registry import BootstrapServiceRegistry

    registry = BootstrapServiceRegistry()

    def raise_on_stop():
        raise RuntimeError("boom")

    registry.register("service", lambda: None, raise_on_stop)
    registry.start_all()

    try:
        registry.stop_all()
    except RuntimeError:
        pass

    assert registry.started_names() == []


def test_bootstrap_services_use_registry_and_skip_duplicate_starts(monkeypatch):
    from app.bootstrap import services

    services.reset_bootstrap_registry()
    calls = []

    def record(name):
        return lambda: calls.append(name)

    monkeypatch.setattr(services, "ensure_strong_webhook_token", record("webhook-token"))
    monkeypatch.setattr(services, "audit_proxy_config", record("proxy-audit"))
    monkeypatch.setattr(services, "start_notification_services", record("notifications"))
    monkeypatch.setattr(services, "stop_notification_services", record("stop:notifications"))
    monkeypatch.setattr(services, "start_user_portal_thread", lambda app, port: calls.append(f"user-portal:{port}"))
    monkeypatch.setattr(services, "stop_user_portal_thread", record("stop:user-portal"))
    monkeypatch.setattr(services, "start_risk_monitor", record("risk-monitor"))
    monkeypatch.setattr(services, "stop_risk_monitor", record("stop:risk-monitor"))
    monkeypatch.setattr(services, "start_dashboard_cache_tasks", record("dashboard-cache"))
    monkeypatch.setattr(services, "stop_dashboard_cache_tasks", record("stop:dashboard-cache"))
    monkeypatch.setattr(services, "start_media_request_services", record("media-requests"))
    monkeypatch.setattr(services, "stop_community_cache_refresh_loop", record("stop:media-requests"))
    monkeypatch.setattr(services, "start_calendar_service", record("calendar"))
    monkeypatch.setattr(services, "stop_calendar_service", record("stop:calendar"))
    monkeypatch.setattr(services, "start_notifications_router_services", record("notifications-router"))
    monkeypatch.setattr(services, "start_calendar_notify_services", record("calendar-notify"))
    monkeypatch.setattr(services.calendar_notify_service, "stop", record("stop:calendar-notify"))
    monkeypatch.setattr(services, "init_dedupe_db", record("dedupe"))
    monkeypatch.setattr(services, "start_gap_services", record("gaps"))
    monkeypatch.setattr(services, "stop_gap_services", record("stop:gaps"))
    monkeypatch.setattr(services, "start_auth_domain_services", record("auth-domain"))
    monkeypatch.setattr(services, "stop_auth_domain_services", record("stop:auth-domain"))
    monkeypatch.setattr(services, "start_user_domain_services", record("user-domain"))
    monkeypatch.setattr(services, "ensure_pro_schema", record("pro-domain"))
    monkeypatch.setattr(services, "start_system_task_services", record("system-tasks"))
    monkeypatch.setattr(services, "stop_task_poller", record("stop:system-tasks"))
    monkeypatch.setattr(services, "init_audit_table", record("audit"))
    monkeypatch.setattr(services, "start_session_services", record("session"))
    monkeypatch.setattr(services, "stop_session_cleanup_loop", record("stop:session"))
    monkeypatch.setattr(services, "disable_enabled_plugins", record("stop:plugin-lifecycle"))
    monkeypatch.setattr(services, "print_startup_panel", lambda port: calls.append(f"startup-panel:{port}"))

    services.start_bootstrap_services(object(), 10308)
    services.start_bootstrap_services(object(), 10309)

    assert calls == [
        "webhook-token",
        "proxy-audit",
        "notifications",
        "user-portal:10308",
        "risk-monitor",
        "dashboard-cache",
        "media-requests",
        "calendar",
        "notifications-router",
        "calendar-notify",
        "dedupe",
        "gaps",
        "auth-domain",
        "user-domain",
        "pro-domain",
        "system-tasks",
        "audit",
        "session",
        "startup-panel:10308",
    ]

    services.stop_bootstrap_services()

    assert calls[-12:] == [
        "stop:plugin-lifecycle",
        "stop:session",
        "stop:system-tasks",
        "stop:auth-domain",
        "stop:gaps",
        "stop:calendar-notify",
        "stop:calendar",
        "stop:media-requests",
        "stop:dashboard-cache",
        "stop:risk-monitor",
        "stop:user-portal",
        "stop:notifications",
    ]
    services.reset_bootstrap_registry()


def test_bootstrap_uses_calendar_notify_owner_without_service_wrapper():
    services_path = _REPO_ROOT / "app/bootstrap/services.py"
    services_source = services_path.read_text(encoding="utf-8")
    tree = ast.parse(services_source, filename=str(services_path))

    assert not (_REPO_ROOT / "app/domains/notifications/calendar_notify_service.py").exists()
    assert (
        "from app.domains.notifications.calendar_notify import "
        "calendar_notify_service, start_calendar_notify_services"
    ) in services_source
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module != "app.domains.notifications.calendar_notify_service"
        elif isinstance(node, ast.Import):
            imported_modules = {alias.name for alias in node.names}
            assert "app.domains.notifications.calendar_notify_service" not in imported_modules
