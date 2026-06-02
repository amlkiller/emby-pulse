import ast
import asyncio
import io
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_reports_router_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/reports/router.py"
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


def test_preview_report_returns_403_when_public_admin_facade_denies(monkeypatch):
    from app.domains.reports import router

    request = SimpleNamespace(session={"user": {"Id": "u1", "Name": "User One"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_generate_report(*args, **kwargs):
        raise AssertionError("report generation should not run without admin permission")

    monkeypatch.setattr(router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(router.report_gen, "generate_report", fail_generate_report)

    response = asyncio.run(router.api_preview_report(request, user_id="u1", period="day"))

    assert response.status_code == 403
    assert calls == [request]


def test_preview_report_returns_jpeg_when_public_admin_facade_allows(monkeypatch):
    from app.domains.reports import router

    request = SimpleNamespace(session={"user": {"Id": "admin", "Name": "Admin"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_generate_report(user_id, period):
        calls.append(("generate_report", user_id, period))
        return io.BytesIO(b"jpeg-bytes")

    monkeypatch.setattr(router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(router, "HAS_PIL", True)
    monkeypatch.setattr(router.report_gen, "generate_report", fake_generate_report)

    response = asyncio.run(router.api_preview_report(request, user_id="u1", period="week"))

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.body == b"jpeg-bytes"
    assert calls == [
        ("is_admin_user", request),
        ("generate_report", "u1", "week"),
    ]


def test_push_report_rejects_non_admin_through_public_admin_facade(monkeypatch):
    from app.domains.reports import router

    request = SimpleNamespace(session={"user": {"Id": "u1", "Name": "User One"}})
    data = router.PushRequestModel(user_id="u1", period="day", theme="dark")
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_push_report_now(*args, **kwargs):
        raise AssertionError("report push should not run without admin permission")

    monkeypatch.setattr(router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(router.notification_service, "push_report_now", fail_push_report_now)

    response = asyncio.run(router.api_push_report(data, request))

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_push_report_allows_admin_through_public_admin_facade(monkeypatch):
    from app.domains.reports import router

    request = SimpleNamespace(session={"user": {"Id": "admin", "Name": "Admin"}})
    data = router.PushRequestModel(user_id="u1", period="week", theme="light")
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_push_report_now(user_id, period, theme):
        calls.append(("push_report_now", user_id, period, theme))
        return True

    monkeypatch.setattr(router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(router.notification_service, "push_report_now", fake_push_report_now)

    response = asyncio.run(router.api_push_report(data, request))

    assert response == {"status": "success"}
    assert calls == [
        ("is_admin_user", request),
        ("push_report_now", "u1", "week", "light"),
    ]
