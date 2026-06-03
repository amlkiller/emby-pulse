# refactor users new route

## Goal

Reduce the mixed responsibility surface in `app/domains/users/router.py` by moving the new-user management route and its dedicated request model into a focused users child router while preserving existing HTTP behavior and compatibility exports.

## Requirements

* Move `POST /api/manage/user/new`, `api_manage_user_new`, and `NewUserModelEx` out of `app/domains/users/router.py` into a dedicated child router module.
* Keep the route path, method, handler name, request model fields/defaults, response dictionaries, permission checks, media health check, cache invalidation, Emby calls, DAO writes, and audit side effects unchanged.
* Keep `app.domains.users.router.api_manage_user_new` and `app.domains.users.router.NewUserModelEx` available as compatibility exports for tests and existing imports.
* Wire dependencies through provider functions so monkeypatches of legacy globals in `users/router.py` still affect the extracted handler.
* Preserve route registration order, especially after update/library routes and before delete/batch/template/list child routers.
* Add focused regression tests for route inclusion/export, route order, and early authorization/health short-circuit behavior.

## Acceptance Criteria

* [ ] `app/domains/users/router.py` no longer defines `api_manage_user_new` or `NewUserModelEx` inline.
* [ ] A new child router owns `api_manage_user_new` and `NewUserModelEx` and is included at the original route position.
* [ ] `router.api_manage_user_new` and `router.NewUserModelEx` remain identical to the child module exports.
* [ ] Non-admin and media-unhealthy requests return the same payloads before create side effects.
* [ ] Existing create failure, success, policy-template, metadata, and audit behavior is preserved.
* [ ] Focused users tests pass.
* [ ] Full test suite passes.

## Technical Approach

Follow the established users child-router pattern:

* Add a focused `new_user_router.py` with `NewUserModelEx`, an `APIRouter`, provider setters, and the existing handler body.
* Import the child handler/model into `users/router.py` for compatibility.
* Configure providers from `users/router.py` with lambdas that resolve legacy globals dynamically.
* Include the child router where the old `POST /api/manage/user/new` route lived.

## Decision (ADR-lite)

**Context**: `docs/架构审计.md` P2 item 5 recommends reducing large mixed-responsibility domain files via small behavior-preserving slices. `users/router.py` still contains new/update/library/batch management flows after recent child-router extractions.

**Decision**: Extract only the new-user route and its dedicated request model. Leave `UserUpdateModelEx`, `BatchActionModelLocal`, and shared policy helpers in `users/router.py` for later focused slices.

**Consequences**: The task reduces router size without expanding the model boundary or changing update/batch behavior. Broader user management service cleanup remains out of scope.

## Out of Scope

* Changing user creation semantics, template fallback behavior, or Emby policy mutation.
* Refactoring update/library/batch routes.
* Changing `clone_policy` behavior or shared policy constants.
* Changing request/response payload shapes or route paths.

## Technical Notes

* Architecture driver: `docs/架构审计.md` P2 item 5.
* Existing pattern references: `app/domains/users/delete_router.py`, `app/domains/users/single_user_router.py`, `app/domains/users/libraries_router.py`, `app/domains/users/pin_router.py`.
* Regression tests live in `tests/test_users_public_service_facade.py`.
