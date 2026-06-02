# proxy router public auth facade boundary

## Goal

Move the proxy router off the private users auth module for its image-cache admin check, using the existing users public facade instead.

## What I already know

* `docs/架构审计.md` P2 calls out cross-domain direct imports as ongoing architecture debt and recommends public service/facade boundaries.
* `app/domains/proxy/router.py` imports `app.domains.users.auth.is_admin_user`.
* The only use in that router is `clear_image_cache`, which returns `{"status": "error", "message": "未授权"}` when the caller is not an admin.
* `app.domains.users.public_service.is_admin_user(request)` already exists and delegates to the private auth implementation.

## Assumptions

* This is a behavior-preserving refactor. Proxy image behavior, cache paths, response shapes, dependencies, and authorization semantics should remain unchanged.
* This task only targets the proxy router boundary; it should not refactor image transport, cache cleanup, or proxy settings.

## Requirements

* Update `app/domains/proxy/router.py` to use `app.domains.users.public_service`.
* Remove the direct `app.domains.users.auth` import from the proxy router.
* Add focused tests that guard the import boundary.
* Add behavior tests proving `clear_image_cache` uses the public admin facade before deleting cache files.
* Keep changes narrow.

## Acceptance Criteria

* [ ] `app/domains/proxy/router.py` has no import from `app.domains.users.auth`.
* [ ] Tests fail if that private import is reintroduced.
* [ ] Tests prove unauthorized callers get the existing `{"status": "error", "message": "未授权"}` response and no cache deletion.
* [ ] Tests prove authorized callers can clear cache files and use the public facade check.
* [ ] Focused tests, compile checks, import checks, and full `tests/` suite pass with the repository `uv run --with-requirements requirements.txt` command pattern.

## Definition of Done

* Code and tests are committed in one work commit.
* Completed task is archived through Trellis.
* Session journal records the work commit.

## Out of Scope

* Refactoring image proxy transport or cache internals.
* Migrating other routers off `users.auth`.
* Changing cache directory settings or cleanup behavior.

## Technical Notes

* Relevant specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/backend/error-handling.md`.
* Relevant thinking guide: `.trellis/spec/guides/cross-layer-thinking-guide.md`.
* Source audit: `docs/架构审计.md` section "P2 问题 / 跨域直接 import 仍然较多".
