# Refactor Users Self Password Route

## Goal

Split the C-end self password HTTP route out of `app/domains/users/router.py` into a small users-domain child router, continuing `docs/架构审计.md` P2 item 5. Preserve the existing route URL, response shape, password validation, media API calls, and compatibility exports.

## Requirements

* Extract `UserPasswordChangeModel` and `api_user_self_password` from `users/router.py` into a domain-local users module.
* Keep the same route path and method: `POST /api/user/password`.
* Keep the same function signature and return behavior.
* Include the new child router from `users/router.py` at the same relative position, after avatar routes and before library visibility / invitation routes.
* Re-export the extracted model and route function from `users/router.py` by importing them.
* Preserve session checks, empty-password handling, password strength validation, old-password authentication, password update media API call, and `safe_error_message(e, "修改失败")`.
* Preserve monkeypatch compatibility by wiring dependencies through providers that read legacy globals from `users/router.py` dynamically.
* Add focused tests for child-router inclusion, compatibility exports, route order, and login/password-validation short-circuit behavior.

## Acceptance Criteria

* [ ] `app/domains/users/router.py` is smaller and delegates the self password route to a child router.
* [ ] `app.domains.users.router.UserPasswordChangeModel` and `api_user_self_password` remain import-compatible.
* [ ] `POST /api/user/password` remains registered on the aggregate users router.
* [ ] Missing `req_user` returns the same login error before validation or media API calls.
* [ ] Invalid new passwords return the password-strength error before media API calls.
* [ ] Focused users tests pass.
* [ ] Full test suite passes.
* [ ] Code/test changes are committed separately from Trellis archive and journal bookkeeping.

## Definition of Done

* Focused regression coverage added or updated for the extracted boundary.
* Verification runs through the locked `uv run` environment.
* No route URL, response shape, validation, or media API semantics change.
* Task is archived and the session is recorded after the code commit.

## Technical Approach

Create `app/domains/users/self_password_router.py` with `router = APIRouter()`, `UserPasswordChangeModel`, `api_user_self_password`, and `set_dependency_providers(...)`. Wire providers for `media_api`, `validate_password_strength`, and `safe_error_message`. Import the child router and compatibility exports from `users/router.py`, then include the child router where the old password route lived.

## Decision (ADR-lite)

Context: `users/router.py` remains a large mixed-responsibility domain router. The self password route is a narrow C-end account-management boundary with isolated validation and media API side effects.

Decision: Extract the self password route as a users-domain child router using the same dynamic provider pattern as other users child routers.

Consequences: The main users router shrinks while preserving legacy imports and monkeypatch behavior. Admin user create/update/delete/batch flows remain in place for later slices.

## Out of Scope

* Changing password strength rules.
* Changing Emby authentication or password update payloads.
* Changing C-end self-avatar behavior.
* Moving admin password/reset or user update routes.

## Technical Notes

* Source requirement: `docs/架构审计.md` P2 item 5 recommends small behavior-preserving slices for large domain files.
* Existing pattern: users child routers expose `router = APIRouter()` plus compatibility imports from `users/router.py`.
* The self password route currently lives beside the avatar child-router include and should remain near that relative route position.
