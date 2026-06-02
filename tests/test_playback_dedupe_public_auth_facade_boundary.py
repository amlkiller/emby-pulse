import ast
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_playback_dedupe_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/playback/dedupe.py"
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


def test_get_scan_status_denies_non_admin_through_public_facade(monkeypatch):
    from app.domains.playback import dedupe

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    monkeypatch.setattr(dedupe.user_service, "is_admin_user", fake_is_admin_user)

    response = asyncio.run(dedupe.get_scan_status(request))

    assert response == {"success": False, "msg": "需要管理员权限"}
    assert calls == [request]


def test_get_scan_status_allows_admin_through_public_facade(monkeypatch):
    from app.domains.playback import dedupe

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    original_scan_state = dedupe.scan_state
    scan_state = {"is_scanning": False, "progress": 7}
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return True

    monkeypatch.setattr(dedupe.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(dedupe, "scan_state", scan_state)

    response = asyncio.run(dedupe.get_scan_status(request))

    assert response == {"success": True, "data": scan_state}
    assert response["data"] is scan_state
    assert dedupe.scan_state is scan_state
    assert original_scan_state is not scan_state
    assert calls == [request]


def test_get_dedupe_config_allows_admin_through_public_facade(monkeypatch):
    from app.domains.playback import dedupe

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    config = {"strategy": "quality", "excluded_libraries": ["lib-1"]}
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_get_dedupe_config_values():
        calls.append(("get_dedupe_config_values",))
        return config

    monkeypatch.setattr(dedupe.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(dedupe, "get_dedupe_config_values", fake_get_dedupe_config_values)

    response = asyncio.run(dedupe.get_dedupe_config(request))

    assert response == {"success": True, "data": config}
    assert calls == [
        ("is_admin_user", request),
        ("get_dedupe_config_values",),
    ]


def test_save_dedupe_config_denies_non_admin_before_writing(monkeypatch):
    from app.domains.playback import dedupe

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    data = dedupe.SaveConfigReq(config={"strategy": "quality"})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_save_dedupe_config_values(*args, **kwargs):
        raise AssertionError("config should not be written without admin permission")

    monkeypatch.setattr(dedupe.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(dedupe, "save_dedupe_config_values", fail_save_dedupe_config_values)

    response = asyncio.run(dedupe.save_dedupe_config(request, data))

    assert response == {"success": False, "msg": "需要管理员权限"}
    assert calls == [request]
