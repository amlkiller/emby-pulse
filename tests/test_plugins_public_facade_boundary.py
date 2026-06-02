import ast
import asyncio
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_plugins_router_does_not_import_private_users_or_system_modules():
    path = _REPO_ROOT / "app/domains/plugins/router.py"
    rel_path = path.relative_to(_REPO_ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))
    violations = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names = {alias.name for alias in node.names}
            if node.module in {
                "app.domains.users.auth",
                "app.domains.system.views",
            }:
                violations.append(f"{rel_path}:{node.lineno}")
            if node.module == "app.domains.users" and ("auth" in imported_names or "*" in imported_names):
                violations.append(f"{rel_path}:{node.lineno}")
            if node.module == "app.domains.system" and ("views" in imported_names or "*" in imported_names):
                violations.append(f"{rel_path}:{node.lineno}")
        elif isinstance(node, ast.Import):
            imported_modules = {alias.name for alias in node.names}
            if "app.domains.users.auth" in imported_modules:
                violations.append(f"{rel_path}:{node.lineno}")
            if "app.domains.system.views" in imported_modules:
                violations.append(f"{rel_path}:{node.lineno}")

    assert violations == []


def test_plugins_page_uses_public_facades_for_permission_and_template(monkeypatch):
    plugins_router = importlib.import_module("app.domains.plugins.router")

    request = SimpleNamespace(session={"user": {"Id": "u1", "Name": "User One"}})
    calls = []

    def fake_check_permission(seen_request, page):
        calls.append(("check_permission", seen_request, page))
        return True

    def fake_get_common_vars(seen_request, active_page):
        calls.append(("get_common_vars", seen_request, active_page))
        return {"active_page": active_page}

    def fake_template_response(template_name, context):
        calls.append(("TemplateResponse", template_name, context))
        return {"template": template_name, "context": context}

    monkeypatch.setattr(plugins_router.user_service, "check_permission", fake_check_permission)
    monkeypatch.setattr(plugins_router.system_service, "get_common_vars", fake_get_common_vars)
    monkeypatch.setattr(plugins_router.templates, "TemplateResponse", fake_template_response)

    response = asyncio.run(plugins_router.plugins_page(request))

    assert response == {
        "template": "plugins.html",
        "context": {"active_page": "plugins"},
    }
    assert calls == [
        ("check_permission", request, "plugins"),
        ("get_common_vars", request, "plugins"),
        ("TemplateResponse", "plugins.html", {"active_page": "plugins"}),
    ]


def test_plugins_page_redirects_unauthenticated_before_permission(monkeypatch):
    plugins_router = importlib.import_module("app.domains.plugins.router")

    request = SimpleNamespace(session={})

    def fail_check_permission(*args, **kwargs):
        raise AssertionError("permission facade should not be called without a user session")

    def fail_get_common_vars(*args, **kwargs):
        raise AssertionError("template context facade should not be called before auth")

    monkeypatch.setattr(plugins_router.user_service, "check_permission", fail_check_permission)
    monkeypatch.setattr(plugins_router.system_service, "get_common_vars", fail_get_common_vars)

    response = asyncio.run(plugins_router.plugins_page(request))

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_plugins_page_redirects_when_public_permission_denies(monkeypatch):
    plugins_router = importlib.import_module("app.domains.plugins.router")

    request = SimpleNamespace(session={"user": {"Id": "u1", "Name": "User One"}})
    calls = []

    def fake_check_permission(seen_request, page):
        calls.append(("check_permission", seen_request, page))
        return False

    def fail_get_common_vars(*args, **kwargs):
        raise AssertionError("template context facade should not be called without permission")

    monkeypatch.setattr(plugins_router.user_service, "check_permission", fake_check_permission)
    monkeypatch.setattr(plugins_router.system_service, "get_common_vars", fail_get_common_vars)

    response = asyncio.run(plugins_router.plugins_page(request))

    assert response.status_code == 303
    assert response.headers["location"] == "/?no_permission=1"
    assert calls == [("check_permission", request, "plugins")]
