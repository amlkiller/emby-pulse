# Refactor Users Tag Router

## Goal

Reduce `app/domains/users/router.py` by extracting the user tag management routes into a domain-local child router while preserving existing route URLs, response shapes, permission checks, DAO calls, and compatibility imports.

## Requirements

- Add `app/domains/users/tag_router.py` for the tag constants, Pydantic models, and route handlers currently defined at the end of `users/router.py`.
- Move these routes without changing their URL paths or HTTP methods:
  - `GET /api/manage/tags`
  - `POST /api/manage/tags`
  - `DELETE /api/manage/tags/{tag_id}`
  - `DELETE /api/manage/tags/name/{tag_name}`
  - `POST /api/manage/user/tags`
  - `GET /api/manage/user/tags`
- Keep compatibility exports from `app.domains.users.router` for:
  - `TAG_COLORS`
  - `TagCreateModel`
  - `UserTagsUpdateModel`
  - `api_get_tags`
  - `api_create_tag`
  - `api_delete_tag`
  - `api_delete_tag_by_name`
  - `api_update_user_tags`
  - `api_get_user_tags`
- Include the new tag router from `users/router.py` so bootstrap route mounting remains unchanged.
- Do not change admin permission behavior, login checks, response dict shapes, tag color values, DAO calls, or timestamp behavior.

## Acceptance Criteria

- [ ] `users/router.py` no longer contains the tag route handler bodies.
- [ ] `tag_router.py` owns the tag constants, models, and handlers.
- [ ] `users.router` still exposes the tag URLs through `router.include_router(...)`.
- [ ] Existing user router/public-service focused tests pass.
- [ ] Full test suite passes before committing.

## Definition of Done

- Compile changed Python files with `uv run python -m compileall`.
- Run an import and route compatibility check through `uv run python -c`.
- Run focused users router/public-service tests.
- Run the full test suite with `uv run pytest tests/ -v`.
- Commit the code/test slice, archive the Trellis task, and record the session journal.

## Technical Approach

Use the compatibility-preserving child-router pattern used by recent route splits: create a sibling router module, import its public names back into the original large module, and include the child router from the existing parent router to preserve bootstrap wiring.

## Out of Scope

- Refactoring user CRUD, invitations, templates, pinned users, request permissions, or audit log routes.
- Changing `user_dao` persistence behavior.
- Reworking `app/bootstrap/routes.py`.
- Replacing the existing `is_admin_user` import strategy outside this small tag slice.

## Technical Notes

- Architecture audit target: `docs/架构审计.md` P2 item 5, small behavior-preserving splits of large domain files.
- Applicable specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`.
- `app/bootstrap/routes.py` mounts `app.domains.users.router`, so the child router should be included from `users/router.py` rather than mounted separately in bootstrap.
