# pwa router public auth facade boundary

## Goal

Move the PWA router off the private users auth module for its admin checks, using the existing users public facade instead.

## What I already know

* `docs/架构审计.md` P2 calls out cross-domain direct imports as ongoing architecture debt and recommends public service/facade boundaries.
* `app/domains/pwa/router.py` imports `app.domains.users.auth.is_admin_user`.
* The admin-gated PWA endpoints are `upload_custom_icon`, `set_default_icon`, `set_app_name`, and `delete_custom_icon`.
* `app.domains.users.public_service.is_admin_user(request)` already exists and delegates to the private auth implementation.

## Assumptions

* This is a behavior-preserving refactor.
* PWA route URLs, response payloads, upload validation, config writes, icon delete behavior, and unauthenticated checks should remain unchanged.
* This task only targets the PWA router auth import boundary.

## Requirements

* Update `app/domains/pwa/router.py` to use `app.domains.users.public_service`.
* Remove the direct `app.domains.users.auth` import from the PWA router.
* Add focused tests that guard the import boundary.
* Add behavior tests proving admin-gated PWA endpoints use the public admin facade while preserving existing unauthorized/admin behavior.
* Keep changes narrow.

## Acceptance Criteria

* [ ] `app/domains/pwa/router.py` has no import from `app.domains.users.auth`.
* [ ] Tests fail if that private import is reintroduced.
* [ ] Tests prove `set_default_icon` raises `403` through the public facade before saving config when admin is denied.
* [ ] Tests prove `set_default_icon` saves the requested icon through the existing config helper when admin is allowed.
* [ ] Tests prove `delete_custom_icon` raises `403` through the public facade before deleting files when admin is denied.
* [ ] Tests prove `delete_custom_icon` deletes an existing custom icon when admin is allowed.
* [ ] Focused tests, compile checks, import checks, private import search, and full `tests/` suite pass with the repository `uv run --with-requirements requirements.txt` command pattern.

## Definition of Done

* Code and tests are committed in one work commit.
* Completed task is archived through Trellis.
* Session journal records the work commit.

## Out of Scope

* Refactoring PWA DAO/config helpers.
* Changing upload file validation or PIL/image parsing.
* Migrating other routers off `users.auth`.
* Changing PWA route URLs or response shapes.

## Technical Notes

* Relevant specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/backend/error-handling.md`.
* Relevant thinking guide: `.trellis/spec/guides/cross-layer-thinking-guide.md`.
* Source audit: `docs/架构审计.md` section "P2 问题 / 跨域直接 import 仍然较多".
