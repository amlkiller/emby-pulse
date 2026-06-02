import ast
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeInvitationDao:
    def __init__(self):
        self.calls = []

    def get_available_registration_invitation(self, code):
        self.calls.append(("get_available_registration_invitation", code))
        return {"code": code, "days": 30}

    def restore_invitation_code_usage(self, code):
        self.calls.append(("restore_invitation_code_usage", code))

    def claim_invitation_usage(self, code, used_by):
        self.calls.append(("claim_invitation_usage", code, used_by))
        return True

    def save_code_registration_meta_and_finish_invitation(
        self,
        code,
        user_id,
        expire_date,
        allow_routes,
        block_routes,
    ):
        self.calls.append(
            (
                "save_code_registration_meta_and_finish_invitation",
                code,
                user_id,
                expire_date,
                allow_routes,
                block_routes,
            )
        )

    def renew_user_with_invitation_code(self, code, used_by, user_id):
        self.calls.append(("renew_user_with_invitation_code", code, used_by, user_id))
        return {"days": 7, "new_exp": "2026-06-09"}, None

    def create_invitation_codes(
        self,
        codes,
        days,
        created_at,
        template_user_id,
        code_type,
        routes,
        route_mode,
        req_free,
        req_free_count,
    ):
        self.calls.append(
            (
                "create_invitation_codes",
                codes,
                days,
                created_at,
                template_user_id,
                code_type,
                routes,
                route_mode,
                req_free,
                req_free_count,
            )
        )

    def list_admin_invitations(self, code_type="all"):
        self.calls.append(("list_admin_invitations", code_type))
        return [{"code": "reg-code", "type": "register"}]

    def list_invitation_usage_stats(self):
        self.calls.append(("list_invitation_usage_stats",))
        return [{"type": "register", "used_count": 0, "used_by": ""}]

    def list_invitation_export_rows(self, code_type="all"):
        self.calls.append(("list_invitation_export_rows", code_type))
        return [{"code": "reg-code", "type": "register", "days": 30}]

    def delete_invitation_codes(self, codes):
        self.calls.append(("delete_invitation_codes", codes))


def test_system_public_service_delegates_invitation_calls(monkeypatch):
    from app.domains.system import public_service

    invitation_dao = FakeInvitationDao()
    monkeypatch.setattr(public_service, "invitation_dao", invitation_dao)

    assert public_service.get_available_registration_invitation("reg-code") == {
        "code": "reg-code",
        "days": 30,
    }
    assert public_service.restore_invitation_code_usage("reg-code") is None
    assert public_service.claim_invitation_usage("reg-code", "User") is True
    assert public_service.save_code_registration_meta_and_finish_invitation(
        "reg-code",
        "u1",
        "2026-07-01",
        "/a",
        "/b",
    ) is None
    assert public_service.renew_user_with_invitation_code("renew-code", "User", "u1") == (
        {"days": 7, "new_exp": "2026-06-09"},
        None,
    )
    assert public_service.create_invitation_codes(
        ["code-1", "code-2"],
        30,
        "2026-06-02T10:00:00",
        "template-user",
        "register",
        "r1,r2",
        "allow",
        1,
        5,
    ) is None
    assert public_service.list_admin_invitations("register") == [
        {"code": "reg-code", "type": "register"}
    ]
    assert public_service.list_invitation_usage_stats() == [
        {"type": "register", "used_count": 0, "used_by": ""}
    ]
    assert public_service.list_invitation_export_rows("renew") == [
        {"code": "reg-code", "type": "register", "days": 30}
    ]
    assert public_service.delete_invitation_codes(["code-1", "code-2"]) is None

    assert invitation_dao.calls == [
        ("get_available_registration_invitation", "reg-code"),
        ("restore_invitation_code_usage", "reg-code"),
        ("claim_invitation_usage", "reg-code", "User"),
        (
            "save_code_registration_meta_and_finish_invitation",
            "reg-code",
            "u1",
            "2026-07-01",
            "/a",
            "/b",
        ),
        ("renew_user_with_invitation_code", "renew-code", "User", "u1"),
        (
            "create_invitation_codes",
            ["code-1", "code-2"],
            30,
            "2026-06-02T10:00:00",
            "template-user",
            "register",
            "r1,r2",
            "allow",
            1,
            5,
        ),
        ("list_admin_invitations", "register"),
        ("list_invitation_usage_stats",),
        ("list_invitation_export_rows", "renew"),
        ("delete_invitation_codes", ["code-1", "code-2"]),
    ]


def test_system_public_service_delegates_common_vars(monkeypatch):
    from app.domains.system import public_service, views

    calls = []
    request = object()

    def fake_get_common_vars(seen_request, active_page, extra_vars=None):
        calls.append((seen_request, active_page, extra_vars))
        return {"active_page": active_page, **(extra_vars or {})}

    monkeypatch.setattr(views, "get_common_vars", fake_get_common_vars)

    assert public_service.get_common_vars(request, "points", {"is_pro": True}) == {
        "active_page": "points",
        "is_pro": True,
    }
    assert calls == [(request, "points", {"is_pro": True})]


def test_selected_external_callers_do_not_import_private_system_invitation_dao():
    checked_paths = [
        _REPO_ROOT / "app/domains/points/router.py",
        _REPO_ROOT / "app/domains/notifications/user_bot_service.py",
    ]
    violations = []

    for path in checked_paths:
        rel_path = path.relative_to(_REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "app.domains.system.invitation_dao":
                    violations.append(f"{rel_path}:{node.lineno}")
                if node.module == "app.domains.system":
                    imported_names = {alias.name for alias in node.names}
                    if "invitation_dao" in imported_names or "*" in imported_names:
                        violations.append(f"{rel_path}:{node.lineno}")

    assert violations == []
