import ast
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeUserDao:
    def __init__(self):
        self.calls = []

    def delete_user_meta_many(self, user_ids):
        self.calls.append(("delete_user_meta_many", user_ids))
        return 2

    def get_user_display_name(self, user_id):
        self.calls.append(("get_user_display_name", user_id))
        return "User Name"

    def list_user_ids_with_expire_date(self):
        self.calls.append(("list_user_ids_with_expire_date",))
        return [{"user_id": "u1"}]

    def list_users_with_expire_date(self):
        self.calls.append(("list_users_with_expire_date",))
        return [{"user_id": "u1", "expire_date": "2026-06-30"}]

    def list_permanent_user_expire_records(self):
        self.calls.append(("list_permanent_user_expire_records",))
        return [{"user_id": "u2", "expire_date": "2099-01-01"}]

    def get_user_meta(self, user_id):
        self.calls.append(("get_user_meta", user_id))
        return {"user_id": user_id}

    def list_all_user_meta(self):
        self.calls.append(("list_all_user_meta",))
        return [{"user_id": "u1"}, {"user_id": "u2"}]

    def upsert_user_meta_fields(self, user_id, fields, created_at):
        self.calls.append(("upsert_user_meta_fields", user_id, fields, created_at))


class FakeUserBotDao:
    def __init__(self):
        self.calls = []

    def get_tg_user_id_by_emby_id(self, emby_user_id):
        self.calls.append(("get_tg_user_id_by_emby_id", emby_user_id))
        return "tg-1"

    def get_binding_by_emby_id(self, emby_user_id):
        self.calls.append(("get_binding_by_emby_id", emby_user_id))
        return {"tg_user_id": "tg-1", "emby_username": "User Name"}


def test_users_public_service_delegates_and_returns(monkeypatch):
    from app.domains.users import public_service

    user_dao = FakeUserDao()
    user_bot_dao = FakeUserBotDao()
    monkeypatch.setattr(public_service, "user_dao", user_dao)
    monkeypatch.setattr(public_service, "user_bot_dao", user_bot_dao)

    assert public_service.delete_user_meta_many(["u1", "u2"]) == 2
    assert public_service.get_user_display_name("u1") == "User Name"
    assert public_service.list_user_ids_with_expire_date() == [{"user_id": "u1"}]
    assert public_service.list_users_with_expire_date() == [
        {"user_id": "u1", "expire_date": "2026-06-30"}
    ]
    assert public_service.list_permanent_user_expire_records() == [
        {"user_id": "u2", "expire_date": "2099-01-01"}
    ]
    assert public_service.get_tg_user_id_by_emby_id("u1") == "tg-1"
    assert public_service.get_binding_by_emby_id("u1") == {
        "tg_user_id": "tg-1",
        "emby_username": "User Name",
    }
    assert public_service.get_user_meta("u1") == {"user_id": "u1"}
    assert public_service.list_all_user_meta() == [{"user_id": "u1"}, {"user_id": "u2"}]
    assert public_service.upsert_user_meta_fields("u1", {"note": "n"}, "2026-06-02") is None

    assert user_dao.calls == [
        ("delete_user_meta_many", ["u1", "u2"]),
        ("get_user_display_name", "u1"),
        ("list_user_ids_with_expire_date",),
        ("list_users_with_expire_date",),
        ("list_permanent_user_expire_records",),
        ("get_user_meta", "u1"),
        ("list_all_user_meta",),
        ("upsert_user_meta_fields", "u1", {"note": "n"}, "2026-06-02"),
    ]
    assert user_bot_dao.calls == [
        ("get_tg_user_id_by_emby_id", "u1"),
        ("get_binding_by_emby_id", "u1"),
    ]


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


def test_users_router_cache_helpers_use_public_service(monkeypatch):
    from app.domains.users import router

    seen = []
    monkeypatch.setattr(router.user_service, "get_emby_users_cached", lambda: ["cached-user"])
    monkeypatch.setattr(router.user_service, "invalidate_emby_users_cache", lambda: seen.append("invalidated"))

    assert router.get_emby_users_cached() == ["cached-user"]
    assert router.invalidate_emby_users_cache() is None
    assert seen == ["invalidated"]


def test_selected_external_callers_do_not_import_private_users_boundaries():
    checked_paths = [
        _REPO_ROOT / "app/plugins/auto_expire/plugin.py",
        _REPO_ROOT / "app/plugins/keep_alive/plugin.py",
        _REPO_ROOT / "app/plugins/user_backup/user_backup_dao.py",
        _REPO_ROOT / "app/domains/media_requests/router.py",
        _REPO_ROOT / "app/domains/notifications/user_bot_service.py",
        _REPO_ROOT / "app/domains/system/views.py",
    ]
    forbidden_imports = {
        "app.domains.users.user_dao",
        "app.domains.users.user_bot_dao",
    }
    violations = []

    for path in checked_paths:
        rel_path = path.relative_to(_REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module in forbidden_imports:
                    violations.append(f"{rel_path}:{node.lineno}")
                if node.module == "app.domains.users.router":
                    imported_names = {alias.name for alias in node.names}
                    if "invalidate_emby_users_cache" in imported_names or "*" in imported_names:
                        violations.append(f"{rel_path}:{node.lineno}")

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
