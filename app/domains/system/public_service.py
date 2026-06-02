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
