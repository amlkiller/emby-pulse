# Refactor Users Libraries Route

## Goal

Split the admin media libraries HTTP route out of `app/domains/users/router.py` into a small users-domain child router, continuing `docs/架构审计.md` P2 item 5. Preserve the existing route URL, response shape, authorization behavior, media API call, and compatibility exports.

## Requirements

* Extract `api_get_libraries` from `users/router.py` into a domain-local users module.
* Keep the same route path and method: `GET /api/manage/libraries`.
* Keep the same function signature and return behavior.
* Include the new child router from `users/router.py` at the same relative position before `/api/manage/users`.
* Re-export `api_get_libraries` from `users/router.py` by importing it.
* Preserve admin check, media API `/Library/VirtualFolders` call, response mapping, media-server error message, and `safe_error_message` mapping.
* Preserve monkeypatch compatibility by wiring dependencies through providers that read legacy globals from `users/router.py` dynamically.
* Add focused tests for child-router inclusion, compatibility export, route order, and non-admin short-circuit behavior.

## Acceptance Criteria

* [ ] `app/domains/users/router.py` is smaller and delegates the libraries route to a child router.
* [ ] `app.domains.users.router.api_get_libraries` remains import-compatible.
* [ ] `GET /api/manage/libraries` remains registered on the aggregate users router.
* [ ] Non-admin requests are denied before media API calls.
* [ ] Focused users tests pass.
* [ ] Full test suite passes.
* [ ] Code/test changes are committed separately from Trellis archive and journal bookkeeping.

## Definition of Done

* Focused regression coverage added or updated for the extracted boundary.
* Verification runs through the locked `uv run` environment.
* No route URL, response shape, authorization, or media API semantics change.
* Task is archived and the session is recorded after the code commit.

## Technical Approach

Create `app/domains/users/libraries_router.py` with `router = APIRouter()`, `api_get_libraries`, and `set_dependency_providers(...)`. Wire providers for `media_api`, `is_admin_user`, and `safe_error_message`. Import the child router and compatibility export from `users/router.py`, then include the child router where the old route lived.

## Decision (ADR-lite)

Context: `users/router.py` remains a large mixed-responsibility domain router. The admin libraries route is a narrow HTTP boundary with one authorization check and one media API read.

Decision: Extract the libraries route as a users-domain child router using the same dynamic provider pattern as other users child routers.

Consequences: The main users router shrinks while preserving legacy imports and monkeypatch behavior. Larger admin user list/update/delete/batch flows remain in place for later slices.

## Out of Scope

* Changing library list response shape.
* Changing media server client behavior.
* Moving `/api/manage/users` or user-management update/delete routes.
* Changing library visibility self-service routes.

## Technical Notes

* Source requirement: `docs/架构审计.md` P2 item 5 recommends small behavior-preserving slices for large domain files.
* Existing pattern: users child routers expose `router = APIRouter()` plus compatibility imports from `users/router.py`.
* The route currently lives immediately before `/api/manage/users`; preserve that relative ordering.
