# Refactor Users List Router

## Goal

Reduce `app/domains/users/router.py` by extracting the standalone `GET /api/users` route into a domain-local child router while preserving the route URL, response shapes, permission checks, media client call, hidden-user behavior, and compatibility imports.

## Requirements

- Add `app/domains/users/list_router.py` for the `GET /api/users` handler currently defined near the end of `users/router.py`.
- Move `GET /api/users` without changing its URL path or HTTP method.
- Keep compatibility export `api_get_users` from `app.domains.users.router`.
- Include the new list router from `users/router.py` so bootstrap route mounting remains unchanged.
- Preserve route registration order relative to the pinned-user route and following request-permission/tag child routers.
- Do not change login checks, admin checks, response dict shapes, media API behavior, hidden-user lookup, sorting, or exception behavior.

## Acceptance Criteria

- [ ] `users/router.py` no longer contains the `api_get_users` handler body.
- [ ] `list_router.py` owns the handler.
- [ ] `users.router` still exposes `GET /api/users` through `router.include_router(...)`.
- [ ] Existing users router/public-service focused tests pass.
- [ ] Full test suite passes before committing.

## Definition of Done

- Compile changed Python files with `uv run python -m compileall`.
- Run an import and route compatibility check through `uv run python -c`.
- Run focused users router/public-service tests.
- Run the full test suite with `uv run pytest tests/ -v`.
- Commit the code/test slice, archive the Trellis task, and record the session journal.

## Technical Approach

Use the compatibility-preserving child-router pattern from recent users route splits: create a sibling router module, import the handler back into the original large module, and include the child router from `users/router.py` at the original route-group position.

## Out of Scope

- Refactoring pinned-user, request-permission, tag, template, invitation, user CRUD, audit log, or batch-management routes.
- Changing media server client behavior or hidden-user settings.
- Reworking `app/bootstrap/routes.py`.

## Technical Notes

- Architecture audit target: `docs/架构审计.md` P2 item 5, small behavior-preserving splits of large domain files.
- Applicable specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`.
