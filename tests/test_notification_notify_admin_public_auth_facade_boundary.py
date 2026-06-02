import ast
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_notification_notify_admin_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/notifications/notify_admin.py"
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


def test_get_notify_rules_denies_non_admin_before_dao_reads(monkeypatch):
    from app.domains.notifications import notify_admin

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_ensure_notify_rules_table():
        raise AssertionError("notify rules table should not be ensured without admin permission")

    def fail_list_notify_rule_rows():
        raise AssertionError("notify rules should not be read without admin permission")

    monkeypatch.setattr(notify_admin.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(notify_admin, "ensure_notify_rules_table", fail_ensure_notify_rules_table)
    monkeypatch.setattr(notify_admin, "list_notify_rule_rows", fail_list_notify_rule_rows)

    response = notify_admin.api_get_notify_rules(request)

    assert response == {"status": "error", "message": "请先登录"}
    assert calls == [request]


def test_get_notify_types_allows_admin_through_public_facade(monkeypatch):
    from app.domains.notifications import notify_admin

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return True

    monkeypatch.setattr(notify_admin.user_service, "is_admin_user", fake_is_admin_user)

    response = notify_admin.api_get_notify_types(request)

    assert response == {
        "status": "success",
        "data": notify_admin.NOTIFY_TYPES,
        "channels": notify_admin.CHANNEL_OPTIONS,
    }
    assert calls == [request]


def test_save_notify_rules_denies_non_admin_before_writing(monkeypatch):
    from app.domains.notifications import notify_admin

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_save_notify_rules(*args, **kwargs):
        raise AssertionError("notify rules should not be saved without admin permission")

    monkeypatch.setattr(notify_admin.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(notify_admin, "save_notify_rules", fail_save_notify_rules)

    response = notify_admin.api_save_notify_rules(request, {"rules": {"request_new": {}}})

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_get_channels_config_allows_admin_through_public_facade(monkeypatch):
    from app.domains.notifications import notify_admin

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    config = {"tg_bot": {"enabled": True}}
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_get_notification_channels_config():
        calls.append(("get_notification_channels_config",))
        return config

    monkeypatch.setattr(notify_admin.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(
        notify_admin,
        "get_notification_channels_config",
        fake_get_notification_channels_config,
    )

    response = notify_admin.api_get_channels_config(request)

    assert response == {"status": "success", "data": config}
    assert calls == [
        ("is_admin_user", request),
        ("get_notification_channels_config",),
    ]


def test_save_channels_config_denies_non_admin_before_writing(monkeypatch):
    from app.domains.notifications import notify_admin

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_set_notification_channels_config(*args, **kwargs):
        raise AssertionError("channels config should not be saved without admin permission")

    monkeypatch.setattr(notify_admin.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(
        notify_admin,
        "set_notification_channels_config",
        fail_set_notification_channels_config,
    )

    response = notify_admin.api_save_channels_config(request, {"tg_bot": {"enabled": True}})

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]
