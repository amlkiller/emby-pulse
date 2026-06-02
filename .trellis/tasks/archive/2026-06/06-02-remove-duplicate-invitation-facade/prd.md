# Remove Duplicate Invitation Facade Method

## Goal

Remove the duplicated forwarding implementation for `save_code_registration_meta_and_finish_invitation` while preserving the public `app.domains.system.public_service` API used by cross-domain callers.

## Scope

- Keep `app.domains.system.public_service.save_code_registration_meta_and_finish_invitation` available.
- Do not make external domains import the private `invitation_dao` module directly.
- Update focused facade tests to match the direct alias behavior.

## Verification

- Compile changed Python files with `uv run`.
- Run the focused public service facade test with `uv run`.
