# Replace Long Invitation DAO Function References

## Goal

Remove the redundant public service exposure for the registration metadata save function and call the actual DAO implementation directly.

## Scope

- Remove `app.domains.system.public_service.save_code_registration_meta_and_finish_invitation`.
- Replace callers with `app.domains.system.invitation_dao.save_code_registration_meta_and_finish_invitation`.
- Remove focused tests that assert the public service re-export exists.

## Verification

- Compile changed Python files with `uv run`.
- Run the focused public service facade test with `uv run`.
