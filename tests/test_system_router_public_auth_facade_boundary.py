import ast
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_system_router_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/system/router.py"
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


def test_diag_config_denies_non_admin_before_reading_sensitive_fields(monkeypatch):
    from app.domains.system import router

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_get_sensitive_env_fields():
        raise AssertionError("sensitive config fields should not be read without admin permission")

    monkeypatch.setattr(router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(router, "get_sensitive_env_fields", fail_get_sensitive_env_fields)

    response = router.api_diag_config(request)

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_get_routes_allows_admin_through_public_facade(monkeypatch):
    from app.domains.system import router

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    routes = [{"name": "Main", "url": "https://example.test"}]
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_get_media_server_routes():
        calls.append(("get_media_server_routes",))
        return routes

    monkeypatch.setattr(router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(router, "get_media_server_routes", fake_get_media_server_routes)

    response = router.api_get_routes(request)

    assert response == {"status": "success", "data": routes}
    assert calls == [
        ("is_admin_user", request),
        ("get_media_server_routes",),
    ]


def test_get_settings_denies_non_admin_before_reading_settings(monkeypatch):
    from app.domains.system import router

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_get_system_settings_sensitive_fields():
        raise AssertionError("settings should not be read without admin permission")

    monkeypatch.setattr(router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(
        router,
        "get_system_settings_sensitive_fields",
        fail_get_system_settings_sensitive_fields,
    )

    response = router.api_get_settings(request)

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_update_settings_denies_non_admin_before_side_effects(monkeypatch):
    from app.domains.system import router

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    data = router.SettingsModel(emby_host="https://example.test", emby_api_key="key")
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_save_config():
        raise AssertionError("settings should not be saved without admin permission")

    def fail_probe_settings(*args, **kwargs):
        raise AssertionError("media server should not be probed without admin permission")

    monkeypatch.setattr(router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(router, "save_config", fail_save_config)
    monkeypatch.setattr(router.media_api, "probe_settings", fail_probe_settings)

    response = router.api_update_settings(data, request)

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_save_dashboard_layout_denies_non_admin_before_request_body(monkeypatch):
    from app.domains.system import router

    class RequestWithFailingJson:
        session = {"user": {"Id": "u1"}}

        async def json(self):
            raise AssertionError("request body should not be read without admin permission")

    request = RequestWithFailingJson()
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_save_dashboard_layout(*args, **kwargs):
        raise AssertionError("dashboard layout should not be saved without admin permission")

    monkeypatch.setattr(router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(router, "save_dashboard_layout", fail_save_dashboard_layout)

    response = asyncio.run(router.api_save_dashboard_layout(request))

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]
