import ast
import asyncio
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_points_router_does_not_import_private_users_auth_or_system_public_service():
    path = _REPO_ROOT / "app/domains/points/router.py"
    rel_path = path.relative_to(_REPO_ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))
    violations = []
    imports_shared_view_context = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "get_point_config":
                    violations.append(f"{rel_path}:{node.lineno}")
        if isinstance(node, ast.ImportFrom):
            imported_names = {alias.name for alias in node.names}
            if node.module == "app.domains.users.auth":
                violations.append(f"{rel_path}:{node.lineno}")
            if node.module == "app.domains.users" and ("auth" in imported_names or "*" in imported_names):
                violations.append(f"{rel_path}:{node.lineno}")
            if node.module == "app.domains.system" and ("public_service" in imported_names or "*" in imported_names):
                violations.append(f"{rel_path}:{node.lineno}")
            if node.module == "app.domains.system.views" and (
                "get_common_vars" in imported_names or "*" in imported_names
            ):
                violations.append(f"{rel_path}:{node.lineno}")
            if node.module == "app.shared.view_context" and "get_common_vars" in imported_names:
                imports_shared_view_context = True
        elif isinstance(node, ast.Import):
            imported_modules = {alias.name for alias in node.names}
            if "app.domains.users.auth" in imported_modules:
                violations.append(f"{rel_path}:{node.lineno}")
            if "app.domains.system.public_service" in imported_modules:
                violations.append(f"{rel_path}:{node.lineno}")
            if "app.domains.system.views" in imported_modules:
                violations.append(f"{rel_path}:{node.lineno}")

    assert violations == []
    assert imports_shared_view_context is True


def test_points_page_uses_permission_facade_and_direct_template_context(monkeypatch):
    from app.domains.points import point_dao

    monkeypatch.setattr(point_dao, "ensure_lottery_table", lambda: None)
    monkeypatch.setattr(point_dao, "ensure_points_schema", lambda: None)
    points_router = importlib.import_module("app.domains.points.router")

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

    monkeypatch.setattr(points_router.user_service, "check_permission", fake_check_permission)
    monkeypatch.setattr(points_router, "get_common_vars", fake_get_common_vars)
    monkeypatch.setattr(points_router.templates, "TemplateResponse", fake_template_response)

    response = asyncio.run(points_router.points_page(request))

    assert response == {
        "template": "points.html",
        "context": {
            "active_page": "points",
            "user": {"Id": "u1", "Name": "User One"},
            "is_pro": True,
        },
    }
    assert calls == [
        ("check_permission", request, "points"),
        (
            "get_common_vars",
            request,
            "points",
            {"user": {"Id": "u1", "Name": "User One"}, "is_pro": True},
        ),
        (
            "TemplateResponse",
            "points.html",
            {
                "active_page": "points",
                "user": {"Id": "u1", "Name": "User One"},
                "is_pro": True,
            },
        ),
    ]
