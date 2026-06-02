# playback insight public auth facade boundary

## Goal

Move the playback insight router off the private users auth module for its admin checks, using the existing users public facade instead.

## What I already know

* `docs/架构审计.md` P2 calls out cross-domain direct imports as ongoing architecture debt and recommends public service/facade boundaries.
* `app/domains/playback/insight.py` imports `app.domains.users.auth.is_admin_user`.
* The insight router has admin-gated ignore-list routes and a quality-scan route.
* `app.domains.users.public_service.is_admin_user(request)` already exists and delegates to the private auth implementation.

## Assumptions

* This is a behavior-preserving refactor.
* Insight route URLs, response payloads, DAO calls, cache behavior, media-server calls, and scan logic should remain unchanged.
* This task only targets the playback insight auth import boundary.

## Requirements

* Update `app/domains/playback/insight.py` to use `app.domains.users.public_service`.
* Remove the direct `app.domains.users.auth` import from the insight router.
* Add focused tests that guard the import boundary.
* Add behavior tests proving representative insight routes use the public admin facade while preserving existing denied/admin behavior.
* Keep changes narrow.

## Acceptance Criteria

* [ ] `app/domains/playback/insight.py` has no import from `app.domains.users.auth`.
* [ ] Tests fail if that private import is reintroduced.
* [ ] Tests prove `ignore_item` returns `{"status": "error", "message": "需要管理员权限"}` through the public facade before writing when admin is denied.
* [ ] Tests prove `ignore_item` writes the same ignore record through the public facade when admin is allowed.
* [ ] Tests prove `get_ignored_items` reads and returns existing ignored rows through the public facade when admin is allowed.
* [ ] Tests prove `scan_library_quality` denies non-admin callers through the public facade before touching scan/cache dependencies.
* [ ] Focused tests, compile checks, import checks, private import search, and full `tests/` suite pass with the repository `uv run --with-requirements requirements.txt` command pattern.

## Definition of Done

* Code and tests are committed in one work commit.
* Completed task is archived through Trellis.
* Session journal records the work commit.

## Out of Scope

* Refactoring quality scan internals.
* Changing insight DAO behavior.
* Migrating other playback modules off `users.auth`.
* Changing insight route URLs or response shapes.

## Technical Notes

* Relevant specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/backend/error-handling.md`.
* Relevant thinking guide: `.trellis/spec/guides/cross-layer-thinking-guide.md`.
* Source audit: `docs/架构审计.md` section "P2 问题 / 跨域直接 import 仍然较多".
