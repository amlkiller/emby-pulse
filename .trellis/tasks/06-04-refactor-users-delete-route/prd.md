# refactor users delete route

## Goal

Reduce the mixed responsibility surface in `app/domains/users/router.py` by moving the single-user delete management route into a focused users child router while preserving existing HTTP behavior, route order, side effects, and compatibility exports.

## Requirements

* Move `DELETE /api/manage/user/{user_id}` and `api_manage_user_delete` out of `app/domains/users/router.py` into a dedicated child router module.
* Keep the route path, method, handler name, response dictionaries, permission checks, password-verification behavior, notification side effects, audit side effects, and error behavior unchanged.
* Keep `app.domains.users.router.api_manage_user_delete` available as a compatibility export for tests and existing imports.
* Wire dependencies through provider functions so monkeypatches of legacy globals in `users/router.py` still affect the extracted handler.
* Preserve route registration order, especially the existing `GET /api/manage/user/{user_id}` before `DELETE /api/manage/user/{user_id}` and before later batch/template/list child routers.
* Add focused regression tests for route inclusion/export, route order, and early authorization/verification short-circuit behavior.

## Acceptance Criteria

* [ ] `app/domains/users/router.py` no longer defines `api_manage_user_delete` inline.
* [ ] A new child router owns `api_manage_user_delete` and is included at the original route position.
* [ ] `router.api_manage_user_delete` remains identical to the child module export.
* [ ] Missing login, non-admin, media health failure, and missing delete-password verification still return the same payloads before delete side effects.
* [ ] Existing delete success and error response shapes are preserved.
* [ ] Focused users tests pass.
* [ ] Full test suite passes.

## Technical Approach

Follow the established users child-router pattern:

* Add a focused `delete_router.py` with an `APIRouter`, provider setters, and the existing handler body.
* Import the child handler into `users/router.py` for compatibility.
* Configure providers from `users/router.py` with lambdas that resolve legacy globals dynamically.
* Include the child router where the old `DELETE /api/manage/user/{user_id}` route lived.

## Decision (ADR-lite)

**Context**: `docs/架构审计.md` P2 item 5 recommends reducing large mixed-responsibility domain files via small behavior-preserving slices. `users/router.py` still contains multiple management route blocks after recent child-router extractions.

**Decision**: Extract only the single-user delete route in this task. Avoid moving `UserUpdateModelEx` or broader update/create/batch flows in the same slice.

**Consequences**: The task keeps the change small and testable while reducing `users/router.py` responsibility. Broader user management service cleanup remains out of scope.

## Out of Scope

* Changing delete-password verification logic, validity windows, or startup-time invalidation.
* Changing notification, audit, media API, DAO, or user cache behavior.
* Refactoring batch delete or other user management write routes.
* Changing request/response payload shapes or route paths.

## Technical Notes

* Architecture driver: `docs/架构审计.md` P2 item 5.
* Existing pattern references: `app/domains/users/single_user_router.py`, `app/domains/users/libraries_router.py`, `app/domains/users/avatar_router.py`, `app/domains/users/pin_router.py`.
* Regression tests live in `tests/test_users_public_service_facade.py` and related users router notification tests.
