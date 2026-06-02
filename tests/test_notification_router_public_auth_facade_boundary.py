import ast
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_notification_router_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/notifications/router.py"
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


def test_get_notifications_denies_non_admin_before_dao_reads(monkeypatch):
    from app.domains.notifications import router as notifications_router

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_count_unread_notifications():
        raise AssertionError("unread notifications should not be counted without admin permission")

    def fail_list_notifications(*args, **kwargs):
        raise AssertionError("notifications should not be listed without admin permission")

    monkeypatch.setattr(notifications_router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(notifications_router, "count_unread_notifications", fail_count_unread_notifications)
    monkeypatch.setattr(notifications_router, "list_notifications", fail_list_notifications)

    response = asyncio.run(notifications_router.get_notifications(request))

    assert response == {"success": False, "msg": "需要管理员权限"}
    assert calls == [request]


def test_get_notifications_allows_admin_through_public_facade(monkeypatch):
    from app.domains.notifications import router as notifications_router

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    notifications = [{"id": 1, "title": "hello"}]
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_count_unread_notifications():
        calls.append(("count_unread_notifications",))
        return 3

    def fake_list_notifications(limit=10, include_cleared=False):
        calls.append(("list_notifications", limit, include_cleared))
        return notifications

    monkeypatch.setattr(notifications_router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(notifications_router, "count_unread_notifications", fake_count_unread_notifications)
    monkeypatch.setattr(notifications_router, "list_notifications", fake_list_notifications)

    response = asyncio.run(notifications_router.get_notifications(request, limit=5, history=True))

    assert response == {"success": True, "unread_count": 3, "items": notifications}
    assert calls == [
        ("is_admin_user", request),
        ("count_unread_notifications",),
        ("list_notifications", 5, True),
    ]


def test_mark_as_read_denies_non_admin_before_writing(monkeypatch):
    from app.domains.notifications import router as notifications_router

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_mark_notifications_read(*args, **kwargs):
        raise AssertionError("notifications should not be marked read without admin permission")

    monkeypatch.setattr(notifications_router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(notifications_router, "mark_notifications_read", fail_mark_notifications_read)

    response = asyncio.run(notifications_router.mark_as_read(notifications_router.MarkReadReq(id=7), request))

    assert response == {"success": False, "msg": "需要管理员权限"}
    assert calls == [request]


def test_clear_notifications_denies_non_admin_before_writing(monkeypatch):
    from app.domains.notifications import router as notifications_router

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_clear_notifications_data():
        raise AssertionError("notifications should not be cleared without admin permission")

    monkeypatch.setattr(notifications_router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(notifications_router, "clear_notifications_data", fail_clear_notifications_data)

    response = asyncio.run(notifications_router.clear_notifications(request))

    assert response == {"success": False, "msg": "需要管理员权限"}
    assert calls == [request]


def test_test_push_notification_allows_admin_through_public_facade(monkeypatch):
    from app.domains.notifications import router as notifications_router

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_ensure_notifications_table():
        calls.append(("ensure_notifications_table",))

    def fake_add_system_notification(**kwargs):
        calls.append(("add_system_notification", kwargs))

    monkeypatch.setattr(notifications_router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(notifications_router, "ensure_notifications_table", fake_ensure_notifications_table)
    monkeypatch.setattr(notifications_router, "add_system_notification", fake_add_system_notification)

    response = asyncio.run(notifications_router.test_push_notification(request))

    assert response == {"success": True, "msg": "测试通知已注入！"}
    assert calls == [
        ("is_admin_user", request),
        ("ensure_notifications_table",),
        (
            "add_system_notification",
            {
                "notify_type": "system",
                "title": "✅ 测试通知成功接入",
                "message": "如果你看到了这条消息，说明从写入到读取的链路已经完全打通！",
                "action_url": "/",
            },
        ),
    ]
