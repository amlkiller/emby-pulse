import ast
import datetime
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeMediaResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeMediaApi:
    def health_check(self):
        return True

    def get(self, path, timeout=None):
        assert path == "/Users/user-1"
        assert timeout == 5
        return FakeMediaResponse(200, {"Name": "Deleted User"})

    def delete(self, path):
        assert path == "/Users/user-1"
        return FakeMediaResponse(204)


def test_users_router_imports_notification_rule_owner_directly():
    path = _REPO_ROOT / "app/domains/users/router.py"
    rel_path = path.relative_to(_REPO_ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))
    imports_notify_admin = False

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names = {alias.name for alias in node.names}
            if node.module == "app.domains.notifications" and "notify_admin" in imported_names:
                imports_notify_admin = True
        elif isinstance(node, ast.Import):
            imported_modules = {alias.name for alias in node.names}
            if "app.domains.notifications.notify_admin" in imported_modules:
                imports_notify_admin = True

    assert imports_notify_admin is True


def test_delete_user_notification_uses_public_rule_before_send_and_preserves_platform(monkeypatch):
    from app.domains.notifications import public_service as notification_service
    from app.domains.users import router
    from app.infra.db import notification_dao

    calls = []
    request = SimpleNamespace(
        session={
            "user": {"id": "admin-1", "name": "Admin User"},
            "delete_verified": True,
            "delete_verified_time": datetime.datetime.now().isoformat(),
        }
    )

    def fake_get_notify_rule(notify_type):
        calls.append(("get_notify_rule", notify_type))
        return {"enabled": 1, "channels": ["tg_bot", "wecom", "web"]}

    def fake_send_message(chat_id, text, platform="all"):
        calls.append(("send_message", chat_id, text, platform))

    def fake_add_system_notification(*args):
        calls.append(("add_system_notification", args))

    monkeypatch.setattr(router, "APP_START_TIME", "2000-01-01T00:00:00")
    monkeypatch.setattr(router, "is_admin_user", lambda request: True)
    monkeypatch.setattr(router, "media_api", FakeMediaApi())
    monkeypatch.setattr(router.user_service, "invalidate_emby_users_cache", lambda: calls.append(("invalidate_cache",)))
    monkeypatch.setattr(
        router,
        "user_dao",
        SimpleNamespace(
            delete_user_meta=lambda user_id: calls.append(("delete_user_meta", user_id)),
            delete_temp_account_by_emby_user=lambda user_id: calls.append(("delete_temp_account", user_id)),
        ),
    )
    monkeypatch.setattr(router, "get_client_ip", lambda request: "127.0.0.1")
    monkeypatch.setattr(router, "add_audit_log", lambda **kwargs: calls.append(("add_audit_log", kwargs)))
    monkeypatch.setattr(router.notify_admin, "get_notify_rule", fake_get_notify_rule)
    monkeypatch.setattr(notification_service, "send_message", fake_send_message)
    monkeypatch.setattr(notification_dao, "add_system_notification", fake_add_system_notification)

    response = router.api_manage_user_delete("user-1", request)

    assert response == {"status": "success", "message": "用户 Deleted User 已删除"}
    assert calls.index(("get_notify_rule", "user_delete")) < next(
        index for index, call in enumerate(calls) if call[0] == "send_message"
    )
    send_message_call = next(call for call in calls if call[0] == "send_message")
    assert send_message_call[1] == "sys_notify"
    assert "Deleted User" in send_message_call[2]
    assert "Admin User" in send_message_call[2]
    assert send_message_call[3] == "all"
