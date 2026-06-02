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


def test_users_router_does_not_define_cache_wrapper_functions():
    path = _REPO_ROOT / "app/domains/users/router.py"
    rel_path = path.relative_to(_REPO_ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))

    wrapper_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in {"get_emby_users_cached", "invalidate_emby_users_cache"}
    }

    assert wrapper_names == set()


def test_users_router_manage_users_uses_public_service_cache_owner(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={"user": {"id": "admin"}})
    calls = []

    def fake_invalidate():
        calls.append(("invalidate_emby_users_cache",))

    def fake_get_users():
        calls.append(("get_emby_users_cached",))
        return [{"Id": "u1", "Name": "User One", "Policy": {}}]

    monkeypatch.setattr(router, "is_admin_user", lambda request: True)
    monkeypatch.setattr(router, "check_expired_users", lambda: calls.append(("check_expired_users",)))
    monkeypatch.setattr(router, "get_media_server_public_host", lambda: "http://emby.local/")
    monkeypatch.setattr(router.user_service, "get_emby_users_cached", fake_get_users)
    monkeypatch.setattr(router.user_service, "invalidate_emby_users_cache", fake_invalidate)
    monkeypatch.setattr(router.user_dao, "list_all_user_meta", lambda: [])
    monkeypatch.setattr(router.user_bot_dao, "list_emby_tg_user_bindings", lambda: [])

    response = router.api_manage_users(request, refresh=True)

    assert response["status"] == "success"
    assert response["emby_url"] == "http://emby.local"
    assert response["data"][0]["Id"] == "u1"
    assert calls == [
        ("check_expired_users",),
        ("invalidate_emby_users_cache",),
        ("get_emby_users_cached",),
    ]


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
