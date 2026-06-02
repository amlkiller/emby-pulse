import ast
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_system_pro_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/system/pro.py"
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


def test_activate_pro_denies_non_admin_through_public_facade(monkeypatch):
    from app.domains.system import pro

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    data = pro.ActivateModel(license_key=" license-key ")
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_machine_id():
        raise AssertionError("machine id should not be read without admin permission")

    def fail_replace_license(*args, **kwargs):
        raise AssertionError("license should not be replaced without admin permission")

    monkeypatch.setattr(pro.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(pro, "get_machine_id", fail_machine_id)
    monkeypatch.setattr(pro, "replace_license", fail_replace_license)

    response = asyncio.run(pro.activate_pro(data, request))

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_activate_pro_allows_admin_through_public_facade(monkeypatch):
    from app.domains.system import pro

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    data = pro.ActivateModel(license_key=" license-key ")
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_replace_license(license_key, machine_id):
        calls.append(("replace_license", license_key, machine_id))

    monkeypatch.setattr(pro.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(pro, "get_machine_id", lambda: "machine-a")
    monkeypatch.setattr(pro, "replace_license", fake_replace_license)
    monkeypatch.setattr(pro, "add_system_notification", lambda *args, **kwargs: None)

    response = asyncio.run(pro.activate_pro(data, request))

    assert response == {"status": "success", "message": "激活成功"}
    assert calls == [
        ("is_admin_user", request),
        ("replace_license", "license-key", "machine-a"),
    ]


def test_get_pro_status_denies_non_admin_through_public_facade(monkeypatch):
    from app.domains.system import pro

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_get_license_status():
        raise AssertionError("license status should not be read without admin permission")

    monkeypatch.setattr(pro.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(pro, "get_license_status", fail_get_license_status)

    response = asyncio.run(pro.get_pro_status(request))

    assert response == {"status": "error", "message": "权限不足"}
    assert calls == [request]
