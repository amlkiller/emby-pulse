import ast
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_system_views_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/system/views.py"
    rel_path = path.relative_to(_REPO_ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))
    violations = []
    imports_shared_view_context = False

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "get_common_vars":
            violations.append(f"{rel_path}:{node.lineno}")
        if isinstance(node, ast.ImportFrom):
            imported_names = {alias.name for alias in node.names}
            if node.module == "app.domains.users.auth":
                violations.append(f"{rel_path}:{node.lineno}")
            if node.module == "app.domains.users" and ("auth" in imported_names or "*" in imported_names):
                violations.append(f"{rel_path}:{node.lineno}")
            if node.module == "app.shared.view_context" and "get_common_vars" in imported_names:
                imports_shared_view_context = True
        elif isinstance(node, ast.Import):
            imported_modules = {alias.name for alias in node.names}
            if "app.domains.users.auth" in imported_modules:
                violations.append(f"{rel_path}:{node.lineno}")

    assert violations == []
    assert imports_shared_view_context is True


def test_check_page_permission_uses_public_facade_for_sub_account(monkeypatch):
    from app.domains.system import views

    request = SimpleNamespace(
        session={
            "user": {
                "name": "User One",
                "auth_type": "local",
                "role": "user",
                "is_admin": False,
                "permissions": ["settings"],
            }
        }
    )
    calls = []

    def fake_get_page_permission_map():
        calls.append(("get_page_permission_map",))
        return {"/settings": "settings"}

    def fake_check_permission(seen_request, page):
        calls.append(("check_permission", seen_request, page))
        return True

    monkeypatch.setattr(views.user_service, "get_page_permission_map", fake_get_page_permission_map)
    monkeypatch.setattr(views.user_service, "check_permission", fake_check_permission)

    response = views.check_page_permission(request, "/settings")

    assert response is None
    assert calls == [
        ("get_page_permission_map",),
        ("check_permission", request, "settings"),
    ]


def test_check_page_permission_denies_through_public_facade(monkeypatch):
    from app.domains.system import views

    request = SimpleNamespace(
        session={
            "user": {
                "name": "Blocked <User>",
                "auth_type": "local",
                "role": "user",
                "is_admin": False,
                "permissions": [],
            }
        }
    )
    calls = []

    def fake_get_page_permission_map():
        calls.append(("get_page_permission_map",))
        return {"/settings": "settings"}

    def fake_check_permission(seen_request, page):
        calls.append(("check_permission", seen_request, page))
        return False

    monkeypatch.setattr(views.user_service, "get_page_permission_map", fake_get_page_permission_map)
    monkeypatch.setattr(views.user_service, "check_permission", fake_check_permission)

    response = views.check_page_permission(request, "/settings")

    assert response.status_code == 403
    assert "Blocked &lt;User&gt;" in response.body.decode("utf-8")
    assert calls == [
        ("get_page_permission_map",),
        ("check_permission", request, "settings"),
    ]


def test_get_first_allowed_page_uses_public_permission_map(monkeypatch):
    from app.domains.system import views

    request = SimpleNamespace(
        session={
            "user": {
                "auth_type": "local",
                "role": "user",
                "permissions": ["clients"],
            }
        }
    )
    calls = []

    def fake_get_page_permission_map():
        calls.append(("get_page_permission_map",))
        return {
            "/content": "content",
            "/clients": "clients",
            "/settings": "settings",
        }

    monkeypatch.setattr(views.user_service, "get_page_permission_map", fake_get_page_permission_map)

    assert views.get_first_allowed_page(request) == "/clients"
    assert calls == [("get_page_permission_map",)]


def test_get_first_allowed_page_keeps_admin_fast_path(monkeypatch):
    from app.domains.system import views

    request = SimpleNamespace(session={"user": {"auth_type": "emby", "role": "admin"}})

    def fail_get_page_permission_map():
        raise AssertionError("permission map should not be read for admin users")

    monkeypatch.setattr(views.user_service, "get_page_permission_map", fail_get_page_permission_map)

    assert views.get_first_allowed_page(request) == "/"
