"""Public system facade for cross-domain callers."""

from app.domains.system import invitation_dao


def get_available_registration_invitation(code: str):
    return invitation_dao.get_available_registration_invitation(code)


def restore_invitation_code_usage(code: str) -> None:
    invitation_dao.restore_invitation_code_usage(code)


def claim_invitation_usage(code: str, used_by: str) -> bool:
    return invitation_dao.claim_invitation_usage(code, used_by)


def save_code_registration_meta_and_finish_invitation(
    code: str,
    user_id: str,
    expire_date,
    allow_routes: str,
    block_routes: str,
) -> None:
    invitation_dao.save_code_registration_meta_and_finish_invitation(
        code,
        user_id,
        expire_date,
        allow_routes,
        block_routes,
    )


def renew_user_with_invitation_code(code: str, used_by: str, user_id: str):
    return invitation_dao.renew_user_with_invitation_code(code, used_by, user_id)


def create_invitation_codes(
    codes,
    days,
    created_at: str,
    template_user_id,
    code_type: str,
    routes: str,
    route_mode: str,
    req_free,
    req_free_count,
) -> None:
    invitation_dao.create_invitation_codes(
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


def list_admin_invitations(code_type: str = "all"):
    return invitation_dao.list_admin_invitations(code_type)


def list_invitation_usage_stats():
    return invitation_dao.list_invitation_usage_stats()


def list_invitation_export_rows(code_type: str = "all"):
    return invitation_dao.list_invitation_export_rows(code_type)


def delete_invitation_codes(codes) -> None:
    invitation_dao.delete_invitation_codes(codes)


def get_common_vars(request, active_page: str, extra_vars: dict = None):
    from app.domains.system.views import get_common_vars as views_get_common_vars

    return views_get_common_vars(request, active_page, extra_vars)
