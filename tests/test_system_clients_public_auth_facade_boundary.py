import ast
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_system_clients_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/system/clients.py"
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


def test_get_blacklist_denies_non_admin_before_dao_read(monkeypatch):
    from app.domains.system import clients

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_list_client_blacklist():
        raise AssertionError("blacklist should not be read without admin permission")

    monkeypatch.setattr(clients.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(clients, "list_client_blacklist", fail_list_client_blacklist)

    response = asyncio.run(clients.get_blacklist(request))

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_get_blacklist_allows_admin_through_public_facade(monkeypatch):
    from app.domains.system import clients

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    rows = [{"app_name": "Infuse"}]
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_list_client_blacklist():
        calls.append(("list_client_blacklist",))
        return rows

    monkeypatch.setattr(clients.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(clients, "list_client_blacklist", fake_list_client_blacklist)

    response = asyncio.run(clients.get_blacklist(request))

    assert response == {"status": "success", "data": rows}
    assert calls == [
        ("is_admin_user", request),
        ("list_client_blacklist",),
    ]


def test_add_blacklist_denies_non_admin_before_writing(monkeypatch):
    from app.domains.system import clients

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    data = clients.BlacklistModel(app_name="Infuse")
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_add_client_blacklist(*args, **kwargs):
        raise AssertionError("blacklist should not be written without admin permission")

    def fail_add_audit_log(*args, **kwargs):
        raise AssertionError("audit log should not be written without admin permission")

    monkeypatch.setattr(clients.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(clients, "add_client_blacklist", fail_add_client_blacklist)
    monkeypatch.setattr(clients, "add_audit_log", fail_add_audit_log)

    response = asyncio.run(clients.add_blacklist(data, request))

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_get_clients_data_allows_admin_through_public_facade_with_cache(monkeypatch):
    from app.domains.system import clients

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    cached = {"status": "success", "devices": []}
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_check_and_block_blacklist_devices():
        calls.append(("check_and_block_blacklist_devices",))

    def fake_get_clients_data_cached():
        calls.append(("get_clients_data_cached",))
        return cached

    monkeypatch.setattr(clients.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(clients, "check_and_block_blacklist_devices", fake_check_and_block_blacklist_devices)
    monkeypatch.setattr(clients, "get_clients_data_cached", fake_get_clients_data_cached)

    response = asyncio.run(clients.get_clients_data(request))

    assert response is cached
    assert calls == [
        ("is_admin_user", request),
        ("check_and_block_blacklist_devices",),
        ("get_clients_data_cached",),
    ]


def test_execute_block_denies_non_admin_before_side_effects(monkeypatch):
    from app.domains.system import clients

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_do_block_devices():
        raise AssertionError("block scan should not run without admin permission")

    def fail_add_audit_log(*args, **kwargs):
        raise AssertionError("audit log should not be written without admin permission")

    monkeypatch.setattr(clients.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(clients, "_do_block_devices", fail_do_block_devices)
    monkeypatch.setattr(clients, "add_audit_log", fail_add_audit_log)

    response = asyncio.run(clients.execute_block(request))

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]
