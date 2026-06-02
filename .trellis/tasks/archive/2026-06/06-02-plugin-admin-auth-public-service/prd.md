# Plugin Admin Auth Public Service Boundary

## Goal

Reduce plugin-to-user-domain internal coupling from `docs/架构审计.md` by moving built-in plugins off the private `app.domains.users.auth` admin-check module and onto the users public facade.

## Requirements

* Expose `is_admin_user(request)` through `app/domains/users/public_service.py`.
* Update built-in plugin modules under `app/plugins/` to call `users.public_service.is_admin_user(...)` instead of importing `app.domains.users.auth`.
* Preserve all current route auth behavior and response shapes.
* Add focused tests proving the users public facade delegates admin checks and plugin modules no longer import `app.domains.users.auth`.

## Acceptance Criteria

* [ ] `app/plugins/**/*.py` no longer imports `app.domains.users.auth`.
* [ ] Plugin admin checks still call the same underlying auth behavior through `users.public_service`.
* [ ] Focused users facade/boundary tests pass.
* [ ] Changed Python files compile through `uv run --with-requirements requirements.txt`.
* [ ] Full pytest suite passes.

## Definition of Done

* No plugin route response or permission behavior changes.
* No new private users DAO/auth imports are introduced in plugin code.
* Work is committed as one coherent refactor commit, then the Trellis task is archived and journaled.

## Technical Approach

Add a thin `is_admin_user(request)` delegator to `app.domains.users.public_service`, importing the current users auth module inside the function to avoid moving auth internals. Replace plugin imports/calls mechanically so each plugin either reuses an existing `user_service` import or imports `public_service as user_service`.

## Out of Scope

* Moving `check_permission` or points page auth/view boundaries.
* Refactoring plugin request handlers.
* Changing login/session semantics.
* Splitting large plugin files.

## Technical Notes

* Audit source: `docs/架构审计.md` P2 item 6 recommends public service/facade boundaries for plugin calls.
* Existing users facade test: `tests/test_users_public_service_facade.py`.
* Current direct plugin import pattern: `from app.domains.users.auth import is_admin_user`.
