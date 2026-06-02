import ast
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_risk_router_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/risk/router.py"
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


def test_get_risk_config_denies_non_admin_through_public_facade(monkeypatch):
    from app.domains.risk import router

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_config_read(*args, **kwargs):
        raise AssertionError("config should not be read without admin permission")

    monkeypatch.setattr(router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(router, "is_risk_control_enabled", fail_config_read)

    response = router.get_risk_config(request)

    assert response == {"error": "需要管理员权限"}
    assert calls == [request]


def test_get_risk_config_allows_admin_through_public_facade(monkeypatch):
    from app.domains.risk import router

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    monkeypatch.setattr(router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(router, "is_risk_control_enabled", lambda: True)
    monkeypatch.setattr(router, "get_default_max_concurrent", lambda: 3)
    monkeypatch.setattr(router, "get_violation_action", lambda: "auto_ban")
    monkeypatch.setattr(router, "is_risk_sys_notification_enabled", lambda: False)

    response = router.get_risk_config(request)

    assert response == {
        "enable_risk_control": True,
        "default_max_concurrent": 3,
        "violation_action": "auto_ban",
        "enable_sys_notification": False,
    }
    assert calls == [("is_admin_user", request)]


def test_update_risk_config_denies_non_admin_before_writing(monkeypatch):
    from app.domains.risk import router

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    data = router.ConfigRequest(
        enable_risk_control=True,
        default_max_concurrent=4,
        violation_action="warn_user",
        enable_sys_notification=False,
    )
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_config_write(*args, **kwargs):
        raise AssertionError("config should not be written without admin permission")

    monkeypatch.setattr(router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(router, "set_risk_control_enabled", fail_config_write)

    with pytest.raises(HTTPException) as exc:
        router.update_risk_config(data, request)

    assert exc.value.status_code == 403
    assert exc.value.detail == "需要管理员权限"
    assert calls == [request]


def test_update_risk_config_allows_admin_through_public_facade(monkeypatch):
    from app.domains.risk import router

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    data = router.ConfigRequest(
        enable_risk_control=True,
        default_max_concurrent=4,
        violation_action="warn_user",
        enable_sys_notification=False,
    )
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    monkeypatch.setattr(router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(
        router,
        "set_risk_control_enabled",
        lambda value: calls.append(("set_risk_control_enabled", value)),
    )
    monkeypatch.setattr(
        router,
        "set_default_max_concurrent",
        lambda value: calls.append(("set_default_max_concurrent", value)),
    )
    monkeypatch.setattr(
        router,
        "set_violation_action",
        lambda value: calls.append(("set_violation_action", value)),
    )
    monkeypatch.setattr(
        router,
        "set_risk_sys_notification_enabled",
        lambda value: calls.append(("set_risk_sys_notification_enabled", value)),
    )

    response = router.update_risk_config(data, request)

    assert response == {"message": "配置已生效"}
    assert calls == [
        ("is_admin_user", request),
        ("set_risk_control_enabled", True),
        ("set_default_max_concurrent", 4),
        ("set_violation_action", "warn_user"),
        ("set_risk_sys_notification_enabled", False),
    ]
