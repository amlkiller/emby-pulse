# Refactor Users Template Router

## Goal

Reduce `app/domains/users/router.py` by extracting the default user-template routes into a domain-local child router while preserving existing route URLs, response shapes, permission checks, config calls, and compatibility imports.

## Requirements

- Add `app/domains/users/template_router.py` for the default-template route handlers currently defined near the end of `users/router.py`.
- Move these routes without changing their URL paths or HTTP methods:
  - `POST /api/manage/template/default`
  - `GET /api/manage/template/default`
- Keep compatibility exports from `app.domains.users.router` for:
  - `api_set_default_template`
  - `api_get_default_template`
- Include the new template router from `users/router.py` so bootstrap route mounting remains unchanged.
- Preserve route registration order relative to the pinned-user route and the following request-permission/tag child routers.
- Do not change the current permission behavior:
  - POST keeps the inline `auth_type != "emby" and role != "admin"` check.
  - GET keeps the `is_admin_user(request)` check.
- Do not change response dict shapes, config getter/setter calls, or error handling.

## Acceptance Criteria

- [ ] `users/router.py` no longer contains the default-template route handler bodies.
- [ ] `template_router.py` owns the default-template handlers.
- [ ] `users.router` still exposes the default-template URLs through `router.include_router(...)`.
- [ ] Existing users router/public-service focused tests pass.
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

- Refactoring pinned-user, request-permission, tag, invitation, user CRUD, audit log, or batch-management routes.
- Changing default-template storage semantics in `app.infra.config.user_bot_settings`.
- Reworking `app/bootstrap/routes.py`.
- Replacing the existing `is_admin_user` import strategy outside this small route slice.

## Technical Notes

- Architecture audit target: `docs/架构审计.md` P2 item 5, small behavior-preserving splits of large domain files.
- Applicable specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`.
- `app/bootstrap/routes.py` mounts `app.domains.users.router`, so the child router should be included from `users/router.py` rather than mounted separately in bootstrap.
