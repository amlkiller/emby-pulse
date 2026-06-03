# refactor users single user route

## Goal

Reduce the mixed responsibility surface in `app/domains/users/router.py` by moving the single-user management lookup route into a focused users child router while preserving existing HTTP behavior and compatibility exports.

## Requirements

* Move `GET /api/manage/user/{user_id}` and `api_get_single_user` out of `app/domains/users/router.py` into a dedicated child router module.
* Keep the route path, method, handler name, response dictionaries, error behavior, and admin authorization behavior unchanged.
* Keep `app.domains.users.router.api_get_single_user` available as a compatibility export for tests and existing imports.
* Wire dependencies through provider functions so monkeypatches of legacy globals in `users/router.py` still affect the extracted handler.
* Preserve route registration order so fixed management routes such as `/api/manage/libraries` and `/api/manage/users` are registered before the dynamic `/api/manage/user/{user_id}` route.
* Add focused regression tests for route inclusion/export, route order, and non-admin short-circuit behavior.

## Acceptance Criteria

* [ ] `app/domains/users/router.py` no longer defines `api_get_single_user` inline.
* [ ] A new child router owns `api_get_single_user` and is included at the original route position.
* [ ] `router.api_get_single_user` remains identical to the child module export.
* [ ] Non-admin requests return `{"status": "error", "message": "需要管理员权限"}` before calling media API or user DAO.
* [ ] Existing response shape for successful, media non-200, and exception paths is preserved.
* [ ] Focused users tests pass.
* [ ] Full test suite passes.

## Technical Approach

Follow the existing users child-router pattern used by `libraries_router.py`, `avatar_router.py`, `self_password_router.py`, and `pin_router.py`:

* Add a focused `single_user_router.py` with an `APIRouter`, provider setters, and the existing handler body.
* Import the child handler into `users/router.py` for compatibility.
* Configure providers from `users/router.py` with lambdas that resolve legacy globals dynamically.
* Include the child router immediately after `/api/manage/users`, matching the old dynamic route position.

## Decision (ADR-lite)

**Context**: `docs/架构审计.md` P2 item 5 calls out large domain files that still mix HTTP entrypoints, orchestration, DAO calls, and response assembly. Recent users slices have established a behavior-preserving child-router extraction pattern.

**Decision**: Continue with a narrow route extraction rather than redesigning users management services in this task.

**Consequences**: This reduces `users/router.py` size and local responsibility without changing public API behavior. Deeper service-layer cleanup remains out of scope for this slice.

## Out of Scope

* Changing HTTP route paths, status payloads, permissions, or media API behavior.
* Refactoring shared user policy mapping or DAO behavior.
* Redesigning users service/facade boundaries beyond this route extraction.
* Addressing other large domain files in the same task.

## Technical Notes

* Architecture driver: `docs/架构审计.md` P2 item 5.
* Existing pattern references: `app/domains/users/libraries_router.py`, `app/domains/users/avatar_router.py`, `app/domains/users/self_password_router.py`, `app/domains/users/pin_router.py`.
* Regression tests live in `tests/test_users_public_service_facade.py`.
