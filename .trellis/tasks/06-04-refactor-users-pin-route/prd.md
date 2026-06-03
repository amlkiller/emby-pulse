# Refactor Users Pin Route

## Goal

Split the user pin HTTP route out of `app/domains/users/router.py` into a small users-domain child router, continuing `docs/架构审计.md` P2 item 5. Preserve the existing route URL, response shape, authorization behavior, audit logging, and compatibility exports.

## Requirements

* Extract `PinUserModel` and `api_pin_user` from `users/router.py` into a domain-local users module.
* Keep the same route path and method: `POST /api/manage/user/pin`.
* Keep the same function signature and return behavior.
* Include the new child router from `users/router.py` at the same relative position, before the existing list/request-permission/tag child routers.
* Re-export the extracted model and route function from `users/router.py` by importing them.
* Preserve session/admin checks, `user_dao.set_user_pinned`, audit logging, client IP lookup, and `safe_error_message` mapping.
* Preserve monkeypatch compatibility by wiring dependencies through providers that read legacy globals from `users/router.py` dynamically.
* Add focused tests for child-router inclusion, compatibility exports, route order, and unauthorized short-circuit behavior.

## Acceptance Criteria

* [ ] `app/domains/users/router.py` is smaller and delegates the pin route to a child router.
* [ ] `app.domains.users.router.PinUserModel` and `api_pin_user` remain import-compatible.
* [ ] `POST /api/manage/user/pin` remains registered on the aggregate users router.
* [ ] Non-admin or unauthenticated requests are denied before DAO, audit, or client-IP side effects.
* [ ] Focused users tests pass.
* [ ] Full test suite passes.
* [ ] Code/test changes are committed separately from Trellis archive and journal bookkeeping.

## Definition of Done

* Focused regression coverage added or updated for the extracted boundary.
* Verification runs through the locked `uv run` environment.
* No route URL, response shape, or authorization semantics change.
* Task is archived and the session is recorded after the code commit.

## Technical Approach

Create `app/domains/users/pin_router.py` with `router = APIRouter()`, `PinUserModel`, `api_pin_user`, and `set_dependency_providers(...)`. Wire providers for `user_dao`, `safe_error_message`, `get_client_ip`, and `add_audit_log`. Import the child router and compatibility exports from `users/router.py`, then include the child router where the old pin route lived.

## Decision (ADR-lite)

Context: `users/router.py` is still over 1,000 lines after prior child-router extractions. The pin route is a narrow HTTP boundary with isolated metadata persistence and audit side effects.

Decision: Extract the pin route as a users-domain child router using the same dynamic provider pattern as other users child routers.

Consequences: The main users router shrinks while preserving monkeypatch-compatible legacy imports. Larger user create/update/delete/batch flows remain in place for later slices.

## Out of Scope

* Changing pin persistence semantics.
* Changing the users list display or pinned remark parsing.
* Moving user create/update/delete/batch routes.
* Changing audit log formatting.

## Technical Notes

* Source requirement: `docs/架构审计.md` P2 item 5 recommends small behavior-preserving slices for large domain files.
* Existing pattern: `users/router.py` imports child routers and compatibility exports for delete verification, invitations, avatar routes, library visibility, lists, permissions, tags, and templates.
* The pin route currently lives near the end of `users/router.py`, before list/request-permission/tag child-router includes.
