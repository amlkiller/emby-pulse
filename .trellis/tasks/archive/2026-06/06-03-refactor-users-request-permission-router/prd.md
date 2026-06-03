# Refactor Users Request Permission Router

## Goal

Reduce `app/domains/users/router.py` by extracting the user request-permission routes into a domain-local child router while preserving existing route URLs, response shapes, permission checks, DAO calls, timestamp behavior, and compatibility imports.

## Requirements

- Add `app/domains/users/request_permission_router.py` for the request-permission Pydantic model and route handlers currently defined near the end of `users/router.py`.
- Move these routes without changing their URL paths or HTTP methods:
  - `POST /api/manage/user/req_permission`
  - `GET /api/manage/user/req_permission`
- Keep compatibility exports from `app.domains.users.router` for:
  - `UserReqPermissionModel`
  - `api_update_user_req_permission`
  - `api_get_user_req_permission`
- Include the new request-permission router from `users/router.py` so bootstrap route mounting remains unchanged.
- Preserve route registration order relative to the following tag router include.
- Do not change admin permission behavior, login checks, response dict shapes, DAO calls, or timestamp behavior.

## Acceptance Criteria

- [ ] `users/router.py` no longer contains the request-permission route handler bodies.
- [ ] `request_permission_router.py` owns the model and handlers.
- [ ] `users.router` still exposes the request-permission URLs through `router.include_router(...)`.
- [ ] Existing user router/public-service focused tests pass.
- [ ] Full test suite passes before committing.

## Definition of Done

- Compile changed Python files with `uv run python -m compileall`.
- Run an import and route compatibility check through `uv run python -c`.
- Run focused users router/public-service tests.
- Run the full test suite with `uv run pytest tests/ -v`.
- Commit the code/test slice, archive the Trellis task, and record the session journal.

## Technical Approach

Use the compatibility-preserving child-router pattern from recent route splits: create a sibling router module, import its public names back into the original large module, and include the child router from the existing parent router at the original route-group position.

## Out of Scope

- Refactoring tag, template, pinned user, invitation, user CRUD, audit log, or batch-management routes.
- Changing `user_dao` persistence behavior.
- Reworking `app/bootstrap/routes.py`.
- Replacing the existing `is_admin_user` import strategy outside this small route slice.

## Technical Notes

- Architecture audit target: `docs/架构审计.md` P2 item 5, small behavior-preserving splits of large domain files.
- Applicable specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`.
- `app/bootstrap/routes.py` mounts `app.domains.users.router`, so the child router should be included from `users/router.py` rather than mounted separately in bootstrap.
