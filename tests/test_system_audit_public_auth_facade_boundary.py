import ast
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_system_audit_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/system/audit.py"
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


def test_audit_page_redirects_unauthenticated_before_admin_check(monkeypatch):
    from app.domains.system import audit

    request = SimpleNamespace(session={})

    def fail_admin_check(*args, **kwargs):
        raise AssertionError("admin check should not run without a logged-in user")

    monkeypatch.setattr(audit.user_service, "is_admin_user", fail_admin_check)

    response = asyncio.run(audit.audit_page(request))

    assert response.status_code == 307
    assert response.headers["location"] == "/login"


def test_audit_page_redirects_non_admin_through_public_facade(monkeypatch):
    from app.domains.system import audit

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_template_response(*args, **kwargs):
        raise AssertionError("audit page should not render without admin permission")

    monkeypatch.setattr(audit.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(audit.templates, "TemplateResponse", fail_template_response)

    response = asyncio.run(audit.audit_page(request))

    assert response.status_code == 307
    assert response.headers["location"] == "/login"
    assert calls == [request]


def test_audit_page_allows_admin_through_public_facade(monkeypatch):
    from app.domains.system import audit

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_template_response(seen_request, template_name, context):
        calls.append(("TemplateResponse", seen_request, template_name, context))
        return {"template": template_name, "context": context}

    monkeypatch.setattr(audit.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(audit.templates, "TemplateResponse", fake_template_response)

    response = asyncio.run(audit.audit_page(request))

    assert response == {
        "template": "audit.html",
        "context": {"request": request, "version": audit.APP_VERSION},
    }
    assert calls == [
        ("is_admin_user", request),
        ("TemplateResponse", request, "audit.html", {"request": request, "version": audit.APP_VERSION}),
    ]


def test_audit_logs_rejects_non_admin_before_reads(monkeypatch):
    from app.domains.system import audit

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_get_audit_logs(*args, **kwargs):
        raise AssertionError("audit logs should not be read without admin permission")

    def fail_list_user_audit_logs_since(*args, **kwargs):
        raise AssertionError("user audit logs should not be read without admin permission")

    monkeypatch.setattr(audit.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(audit, "get_audit_logs", fail_get_audit_logs)
    monkeypatch.setattr(audit, "list_user_audit_logs_since", fail_list_user_audit_logs_since)

    response = asyncio.run(audit.api_get_audit_logs(request))

    assert response.status_code == 403
    assert json.loads(response.body) == {"error": "需要管理员权限"}
    assert calls == [request]


def test_audit_stats_allows_admin_through_public_facade(monkeypatch):
    from app.domains.system import audit

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_get_audit_stats(days):
        calls.append(("get_audit_stats", days))
        return {"login": 2}

    monkeypatch.setattr(audit.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(audit, "get_audit_stats", fake_get_audit_stats)

    response = asyncio.run(audit.api_get_audit_stats(request, days=3))

    assert response == {"status": "success", "data": {"login": 2}}
    assert calls == [
        ("is_admin_user", request),
        ("get_audit_stats", 3),
    ]


def test_audit_actions_allows_admin_through_public_facade(monkeypatch):
    from app.domains.system import audit

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return True

    monkeypatch.setattr(audit.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(audit, "AUDIT_ACTIONS", ["login", "logout"])

    response = asyncio.run(audit.api_get_audit_actions(request))

    assert response == {"status": "success", "data": ["login", "logout"]}
    assert calls == [request]
