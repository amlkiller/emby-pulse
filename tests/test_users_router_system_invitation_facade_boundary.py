import ast
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_users_router_imports_invitation_dao_directly_without_system_public_service():
    path = _REPO_ROOT / "app/domains/users/router.py"
    rel_path = path.relative_to(_REPO_ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))
    violations = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names = {alias.name for alias in node.names}
            if node.module == "app.domains.system.public_service":
                violations.append(f"{rel_path}:{node.lineno}")
            if node.module == "app.domains.system" and (
                "public_service" in imported_names or "*" in imported_names
            ):
                violations.append(f"{rel_path}:{node.lineno}")
        elif isinstance(node, ast.Import):
            imported_modules = {alias.name for alias in node.names}
            if "app.domains.system.public_service" in imported_modules:
                violations.append(f"{rel_path}:{node.lineno}")

    assert violations == []


def test_get_invites_denies_non_admin_before_invitation_dao_side_effects(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return False

    def fail_invitation_dao_call(*args, **kwargs):
        raise AssertionError("invitation_dao should not be called without admin permission")

    monkeypatch.setattr(router, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(
        router,
        "invitation_dao",
        SimpleNamespace(
            list_admin_invitations=fail_invitation_dao_call,
            list_invitation_usage_stats=fail_invitation_dao_call,
        ),
    )

    response = router.api_get_invites(request, code_type="register")

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [("is_admin_user", request)]


def test_get_invites_admin_success_uses_invitation_dao_and_preserves_response(monkeypatch):
    from app.domains.users import router

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []
    invite_rows = [
        {
            "code": "reg-1",
            "type": "register",
            "days": 30,
            "created_at": "2026-06-02T10:00:00",
        },
        {
            "code": "renew-1",
            "type": "renew",
            "days": 7,
            "created_at": "2026-06-01T10:00:00",
        },
    ]
    usage_rows = [
        {"type": "register", "used_count": 0, "used_by": ""},
        {"type": "register", "used_count": 1, "used_by": "User One"},
        {"type": "renew", "used_count": 0, "used_by": "User Two"},
    ]

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_list_admin_invitations(code_type):
        calls.append(("list_admin_invitations", code_type))
        return invite_rows

    def fake_get_user_portal_url():
        calls.append(("get_user_portal_url",))
        return "https://portal.example.test/"

    def fake_list_invitation_usage_stats():
        calls.append(("list_invitation_usage_stats",))
        return usage_rows

    monkeypatch.setattr(router, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(router, "get_user_portal_url", fake_get_user_portal_url)
    monkeypatch.setattr(
        router,
        "invitation_dao",
        SimpleNamespace(
            list_admin_invitations=fake_list_admin_invitations,
            list_invitation_usage_stats=fake_list_invitation_usage_stats,
        ),
    )

    response = router.api_get_invites(request, code_type="register")

    assert response == {
        "status": "success",
        "data": [
            {
                "code": "reg-1",
                "type": "register",
                "days": 30,
                "created_at": "2026-06-02T10:00:00",
                "invite_link": "https://portal.example.test/invite/reg-1",
            },
            {
                "code": "renew-1",
                "type": "renew",
                "days": 7,
                "created_at": "2026-06-01T10:00:00",
            },
        ],
        "stats": {
            "all": {"total": 3, "used": 2, "unused": 1},
            "register": {"total": 2, "used": 1, "unused": 1},
            "renew": {"total": 1, "used": 1, "unused": 0},
        },
    }
    assert calls == [
        ("is_admin_user", request),
        ("list_admin_invitations", "register"),
        ("get_user_portal_url",),
        ("list_invitation_usage_stats",),
    ]
