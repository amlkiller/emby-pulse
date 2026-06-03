import ast
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_users_public_service_emby_users_cache_and_invalidate(monkeypatch):
    from app.domains.users import public_service

    calls = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return [{"Id": "u1", "Name": "User One"}]

    def fake_get(path, timeout):
        calls.append((path, timeout))
        return FakeResponse()

    monkeypatch.setattr(public_service, "_emby_users_cache", {"data": None, "expires": 0})
    monkeypatch.setattr(public_service, "time", SimpleNamespace(time=lambda: 100))
    monkeypatch.setattr(public_service.media_api, "get", fake_get)

    assert public_service.get_emby_users_cached() == [{"Id": "u1", "Name": "User One"}]
    assert public_service.get_emby_users_cached() == [{"Id": "u1", "Name": "User One"}]
    assert calls == [("/Users", 5)]

    public_service.invalidate_emby_users_cache()
    assert public_service._emby_users_cache == {"data": None, "expires": 0}


def test_users_public_service_delegates_admin_check(monkeypatch):
    from app.domains.users import auth, public_service

    calls = []
    request = object()

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return True

    monkeypatch.setattr(auth, "is_admin_user", fake_is_admin_user)

    assert public_service.is_admin_user(request) is True
    assert calls == [request]


def test_users_public_service_delegates_permission_check(monkeypatch):
    from app.domains.users import auth, public_service

    calls = []
    request = object()

    def fake_check_permission(seen_request, page):
        calls.append((seen_request, page))
        return True

    monkeypatch.setattr(auth, "check_permission", fake_check_permission)

    assert public_service.check_permission(request, "points") is True
    assert calls == [(request, "points")]


def test_users_public_service_exposes_page_permission_map(monkeypatch):
    from app.domains.users import auth, public_service

    permission_map = {"/settings": "settings", "/clients": "clients"}
    monkeypatch.setattr(auth, "PAGE_PERMISSION_MAP", permission_map)

    assert public_service.get_page_permission_map() is permission_map


def test_users_router_uses_public_service_cache_owner():
    path = _REPO_ROOT / "app/domains/users/router.py"
    source = path.read_text(encoding="utf-8")

    assert "def get_emby_users_cached(" not in source
    assert "def invalidate_emby_users_cache(" not in source
    assert "user_service.get_emby_users_cached()" in source
    assert "user_service.invalidate_emby_users_cache()" in source


def test_users_router_includes_tag_routes():
    from app.domains.users import router

    routes = [(route.path, route.methods) for route in router.router.routes if hasattr(route, "methods")]

    assert any(path == "/api/manage/template/default" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/manage/template/default" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/manage/user/req_permission" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/manage/user/req_permission" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/manage/tags" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/manage/tags" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/manage/tags/{tag_id}" and "DELETE" in methods for path, methods in routes)
    assert any(path == "/api/manage/tags/name/{tag_name}" and "DELETE" in methods for path, methods in routes)
    assert any(path == "/api/manage/user/tags" and "POST" in methods for path, methods in routes)
    assert any(path == "/api/manage/user/tags" and "GET" in methods for path, methods in routes)


def test_selected_external_callers_use_real_user_dao_for_persistence_calls():
    checked_paths = [
        _REPO_ROOT / "app/plugins/auto_expire/plugin.py",
        _REPO_ROOT / "app/plugins/keep_alive/plugin.py",
        _REPO_ROOT / "app/plugins/user_backup/user_backup_dao.py",
        _REPO_ROOT / "app/domains/media_requests/router.py",
        _REPO_ROOT / "app/domains/notifications/user_bot_service.py",
        _REPO_ROOT / "app/domains/system/views.py",
    ]
    violations = []

    for path in checked_paths:
        rel_path = path.relative_to(_REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "app.domains.users.router":
                    imported_names = {alias.name for alias in node.names}
                    if "invalidate_emby_users_cache" in imported_names or "*" in imported_names:
                        violations.append(f"{rel_path}:{node.lineno}")
                if node.module == "app.domains.users":
                    imported_names = {alias.name for alias in node.names}
                    if "public_service" in imported_names:
                        continue

    assert violations == []


def test_plugins_do_not_import_private_users_auth_boundary():
    violations = []

    for path in (_REPO_ROOT / "app/plugins").rglob("*.py"):
        rel_path = path.relative_to(_REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "app.domains.users.auth":
                violations.append(f"{rel_path}:{node.lineno}")

    assert violations == []
