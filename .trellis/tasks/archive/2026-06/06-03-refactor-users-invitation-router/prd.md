# Refactor Users Invitation Router

## Goal

Continue the architecture audit P2 large-domain-file cleanup by extracting invitation-code management endpoints from `app/domains/users/router.py` into a users-domain child router while preserving existing route behavior and compatibility imports.

## Requirements

* Add a new users-domain module for invitation management routes.
* Move these endpoints out of `app/domains/users/router.py`:
  * `POST /api/manage/invite/gen`
  * `GET /api/manage/invites`
  * `GET /api/manage/invites/export`
  * `POST /api/manage/invites/batch`
* Preserve route URLs, methods, request models, session/admin checks, response shapes, CSV export behavior, invitation DAO calls, audit logging calls, portal URL handling, generated-code behavior, and exception handling.
* Keep `app.domains.users.router` compatibility exports for moved endpoint functions and invitation request models.
* Preserve existing monkeypatch compatibility for direct calls through `app.domains.users.router`, including `is_admin_user`, `invitation_dao`, `get_user_portal_url`, `get_client_ip`, and `add_audit_log`.
* Include the new child router from `app/domains/users/router.py` at the original route position between user hidden-library routes and later user-management routes.
* Keep the slice narrow; do not refactor user creation/update/delete, library, avatar, or media API flows.

## Acceptance Criteria

* [ ] `app/domains/users/router.py` no longer defines the four invitation route bodies directly.
* [ ] The four invitation routes remain registered through `app.domains.users.router.router`.
* [ ] Moved functions and request models remain importable from `app.domains.users.router`.
* [ ] Existing invitation tests that monkeypatch `users.router` continue to pass.
* [ ] Focused compile/import/route checks pass.
* [ ] Relevant users router tests pass.
* [ ] The full test suite passes before commit.

## Definition of Done

* Tests added or updated where useful to lock route inclusion and compatibility exports.
* Compile/import checks pass for changed modules.
* `git diff --check` passes.
* No spec update is needed unless the work discovers a new project convention or gotcha.
* Code changes are committed before task archive and journal bookkeeping.

## Technical Approach

Create `app/domains/users/invitation_router.py` with its own `APIRouter`, move the invitation models and route functions there, and import the moved names plus child router back into `users/router.py`. Configure dependency providers from `users/router.py` so direct calls to re-exported functions still observe monkeypatches applied to the old module globals.

## Out of Scope

* Changing invitation-code schema, usage semantics, or CSV field order.
* Changing audit log content.
* Changing administrator authorization policy.
* Refactoring unrelated users-domain routes.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Existing users child-router pattern: `audit_log_router.py`, `delete_verification_router.py`, `list_router.py`, `request_permission_router.py`, `tag_router.py`, and `template_router.py`.
* Existing tests in `tests/test_users_router_system_invitation_facade_boundary.py` directly monkeypatch `app.domains.users.router` globals before calling `router.api_get_invites`; preserve that compatibility.
