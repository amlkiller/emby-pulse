import ast
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_notification_calendar_notify_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/notifications/calendar_notify.py"
    rel_path = path.relative_to(_REPO_ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))
    violations = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names = {alias.name for alias in node.names}
            if node.module == "app.domains.users.auth":
                violations.append(f"{rel_path}:{node.lineno}")
            if node.module == "app.domains.users" and ("auth" in imported_names or "*" in imported_names):
                violations.append(f"{rel_path}:{node.lineno}")
        elif isinstance(node, ast.Import):
            imported_modules = {alias.name for alias in node.names}
            if "app.domains.users.auth" in imported_modules:
                violations.append(f"{rel_path}:{node.lineno}")

    assert violations == []


def test_get_notify_config_denies_non_admin_before_config_read(monkeypatch):
    from app.domains.notifications import calendar_notify

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_get_calendar_notify_config():
        raise AssertionError("calendar notify config should not be read without admin permission")

    monkeypatch.setattr(calendar_notify.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(calendar_notify, "get_calendar_notify_config", fail_get_calendar_notify_config)

    response = calendar_notify.get_notify_config(request)

    assert response == {"status": "error", "message": "未授权"}
    assert calls == [request]


def test_get_notify_config_allows_admin_through_public_facade(monkeypatch):
    from app.domains.notifications import calendar_notify

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    row = {
        "enabled": 1,
        "notify_time": "08:30",
        "channels": '["tg_bot", "wecom"]',
        "tg_chat_id": "chat-1",
        "wecom_touser": "@all",
        "last_sent": "2026-06-02 08:30:00",
    }
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_get_calendar_notify_config():
        calls.append(("get_calendar_notify_config",))
        return row

    monkeypatch.setattr(calendar_notify.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(calendar_notify, "get_calendar_notify_config", fake_get_calendar_notify_config)

    response = calendar_notify.get_notify_config(request)

    assert response == {
        "status": "success",
        "data": {
            "enabled": True,
            "notify_time": "08:30",
            "channels": ["tg_bot", "wecom"],
            "tg_chat_id": "chat-1",
            "wecom_touser": "@all",
            "last_sent": "2026-06-02 08:30:00",
        },
    }
    assert calls == [
        ("is_admin_user", request),
        ("get_calendar_notify_config",),
    ]


def test_save_notify_config_denies_non_admin_before_writing(monkeypatch):
    from app.domains.notifications import calendar_notify

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    config = calendar_notify.CalendarNotifyConfig(enabled=True, notify_time="08:30")
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_save_calendar_notify_config(*args, **kwargs):
        raise AssertionError("calendar notify config should not be saved without admin permission")

    def fail_init_calendar_notify_service():
        raise AssertionError("calendar notify service should not restart without admin permission")

    monkeypatch.setattr(calendar_notify.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(calendar_notify, "save_calendar_notify_config", fail_save_calendar_notify_config)
    monkeypatch.setattr(calendar_notify, "init_calendar_notify_service", fail_init_calendar_notify_service)

    response = calendar_notify.save_notify_config(request, config)

    assert response == {"status": "error", "message": "未授权"}
    assert calls == [request]


def test_test_notify_denies_non_admin_before_send(monkeypatch):
    from app.domains.notifications import calendar_notify

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_send_calendar_notify(*args, **kwargs):
        raise AssertionError("calendar notification should not send without admin permission")

    monkeypatch.setattr(calendar_notify.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(calendar_notify, "send_calendar_notify", fail_send_calendar_notify)

    response = calendar_notify.test_notify(request)

    assert response == {"status": "error", "message": "未授权"}
    assert calls == [request]


def test_manual_send_allows_admin_through_public_facade(monkeypatch):
    from app.domains.notifications import calendar_notify

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_send_calendar_notify(test=False):
        calls.append(("send_calendar_notify", test))
        return {"success": True, "message": "已发送至: TG机器人"}

    monkeypatch.setattr(calendar_notify.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(calendar_notify, "send_calendar_notify", fake_send_calendar_notify)

    response = calendar_notify.manual_send(request)

    assert response == {"status": "success", "message": "通知已发送: 已发送至: TG机器人"}
    assert calls == [
        ("is_admin_user", request),
        ("send_calendar_notify", False),
    ]
