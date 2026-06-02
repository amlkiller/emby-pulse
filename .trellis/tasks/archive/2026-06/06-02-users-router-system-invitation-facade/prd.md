# Users Router System Invitation Public Facade Boundary

## Goal

Move `app/domains/users/router.py` invitation-code management calls off the private system invitation DAO and through the system public facade, preserving existing user/admin invitation API behavior.

## Requirements

- Replace `from app.domains.system import invitation_dao` in `app/domains/users/router.py` with the system public facade.
- Route all existing users-router invitation-code DAO calls through `app.domains.system.public_service`.
- Add any missing narrow delegation functions to `app/domains/system/public_service.py` needed by the users router.
- Preserve endpoint paths, response payloads/messages, audit logging, generated links, CSV/export behavior, and side-effect ordering.
- Add focused regression tests that prove:
  - `users/router.py` no longer imports private `system.invitation_dao`.
  - Representative non-admin invitation admin routes deny before system facade/DAO side effects.
  - Representative admin success routes call through the system public facade and preserve response shape/order.

## Acceptance Criteria

- [ ] `users/router.py` has no direct `app.domains.system.invitation_dao` import.
- [ ] Invitation-code admin APIs still return the same unauthorized payloads.
- [ ] Admin success paths still call existing helpers in the same order through the public facade.
- [ ] System public facade has focused delegation coverage for any new functions.
- [ ] Focused boundary tests pass.
- [ ] Compile, import, private-import scan, and full pytest suite pass before commit.

## Definition of Done

- Tests added/updated for the import boundary and representative authorization/facade behavior.
- Python verification commands use `uv run`.
- Work commit is created for code/test files, followed by separate Trellis archive and journal commits.

## Technical Approach

Import `app.domains.system.public_service` as `system_service` in `users/router.py`, replace invitation DAO calls with `system_service.*` wrappers, and keep the new system public facade functions as thin delegations to `invitation_dao`.

## Out of Scope

- No endpoint, schema, response, audit, invitation-code generation, CSV/export, or user-registration behavior changes.
- No migration of users-domain-local DAO imports.
- No larger split of `users/router.py`.

## Technical Notes

- Audit source: `docs/架构审计.md` P2 issue 6, cross-domain private import cleanup.
- Target files inspected:
  - `app/domains/users/router.py`
  - `app/domains/system/public_service.py`
- Existing local test style:
  - `tests/test_system_public_service_facade.py`
  - `tests/test_users_public_service_facade.py`
  - `tests/test_*_public_auth_facade_boundary.py`
