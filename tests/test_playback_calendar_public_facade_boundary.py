import ast
import asyncio
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_calendar_router_does_not_import_private_users_auth_or_system_public_service():
    path = _REPO_ROOT / "app/domains/playback/calendar.py"
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
            if node.module == "app.domains.system" and ("public_service" in imported_names or "*" in imported_names):
                violations.append(f"{rel_path}:{node.lineno}")
        elif isinstance(node, ast.Import):
            imported_modules = {alias.name for alias in node.names}
            if "app.domains.users.auth" in imported_modules:
                violations.append(f"{rel_path}:{node.lineno}")
            if "app.domains.system.public_service" in imported_modules:
                violations.append(f"{rel_path}:{node.lineno}")

    assert violations == []


def test_calendar_page_uses_permission_facade_and_direct_template_context(monkeypatch):
    calendar_router = importlib.import_module("app.domains.playback.calendar")

    request = SimpleNamespace(session={"user": {"Id": "u1", "Name": "User One"}})
    calls = []

    def fake_check_permission(seen_request, page):
        calls.append(("check_permission", seen_request, page))
        return True

    def fake_get_common_vars(seen_request, active_page, extra_vars):
        calls.append(("get_common_vars", seen_request, active_page, extra_vars))
        return {"active_page": active_page, **extra_vars}

    def fake_template_response(template_name, context):
        calls.append(("TemplateResponse", template_name, context))
        return {"template": template_name, "context": context}

    monkeypatch.setattr(calendar_router.user_service, "check_permission", fake_check_permission)
    monkeypatch.setattr(calendar_router, "get_common_vars", fake_get_common_vars)
    monkeypatch.setattr(calendar_router, "get_calendar_public_url", lambda: "https://calendar.example/")
    monkeypatch.setattr(calendar_router.templates, "TemplateResponse", fake_template_response)

    response = asyncio.run(calendar_router.calendar_page(request))

    assert response == {
        "template": "calendar.html",
        "context": {
            "active_page": "calendar",
            "emby_public_url": "https://calendar.example",
            "is_pro": True,
        },
    }
    assert calls == [
        ("check_permission", request, "calendar"),
        (
            "get_common_vars",
            request,
            "calendar",
            {"emby_public_url": "https://calendar.example", "is_pro": True},
        ),
        (
            "TemplateResponse",
            "calendar.html",
            {
                "active_page": "calendar",
                "emby_public_url": "https://calendar.example",
                "is_pro": True,
            },
        ),
    ]


def test_calendar_page_redirects_unauthenticated_before_permission(monkeypatch):
    calendar_router = importlib.import_module("app.domains.playback.calendar")

    request = SimpleNamespace(session={})

    def fail_check_permission(*args, **kwargs):
        raise AssertionError("permission facade should not be called without a user session")

    def fail_get_common_vars(*args, **kwargs):
        raise AssertionError("template context facade should not be called before auth")

    monkeypatch.setattr(calendar_router.user_service, "check_permission", fail_check_permission)
    monkeypatch.setattr(calendar_router, "get_common_vars", fail_get_common_vars)

    response = asyncio.run(calendar_router.calendar_page(request))

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_calendar_page_redirects_when_public_permission_denies(monkeypatch):
    calendar_router = importlib.import_module("app.domains.playback.calendar")

    request = SimpleNamespace(session={"user": {"Id": "u1", "Name": "User One"}})
    calls = []

    def fake_check_permission(seen_request, page):
        calls.append(("check_permission", seen_request, page))
        return False

    def fail_get_common_vars(*args, **kwargs):
        raise AssertionError("template context facade should not be called without permission")

    monkeypatch.setattr(calendar_router.user_service, "check_permission", fake_check_permission)
    monkeypatch.setattr(calendar_router, "get_common_vars", fail_get_common_vars)

    response = asyncio.run(calendar_router.calendar_page(request))

    assert response.status_code == 303
    assert response.headers["location"] == "/?no_permission=1"
    assert calls == [("check_permission", request, "calendar")]


def test_update_calendar_config_uses_public_admin_facade_before_updating_ttl(monkeypatch):
    calendar_router = importlib.import_module("app.domains.playback.calendar")

    request = SimpleNamespace(session={"user": {"Id": "admin", "Name": "Admin"}})
    config = calendar_router.CalendarConfigReq(ttl=1800)
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_set_calendar_cache_ttl(ttl):
        calls.append(("set_calendar_cache_ttl", ttl))

    monkeypatch.setattr(calendar_router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(calendar_router, "set_calendar_cache_ttl", fake_set_calendar_cache_ttl)

    response = asyncio.run(calendar_router.update_calendar_config(request, config))

    assert response == {"status": "success"}
    assert calls == [
        ("is_admin_user", request),
        ("set_calendar_cache_ttl", 1800),
    ]


def test_update_calendar_config_rejects_when_public_admin_facade_denies(monkeypatch):
    calendar_router = importlib.import_module("app.domains.playback.calendar")

    request = SimpleNamespace(session={"user": {"Id": "u1", "Name": "User One"}})
    config = calendar_router.CalendarConfigReq(ttl=1800)
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return False

    def fail_set_calendar_cache_ttl(*args, **kwargs):
        raise AssertionError("calendar ttl should not be updated without admin permission")

    monkeypatch.setattr(calendar_router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(calendar_router, "set_calendar_cache_ttl", fail_set_calendar_cache_ttl)

    response = asyncio.run(calendar_router.update_calendar_config(request, config))

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [("is_admin_user", request)]
