# playback dedupe public auth facade boundary

## Goal

Move the playback dedupe router off the private users auth module for its admin checks, using the existing users public facade instead.

## What I already know

* `docs/架构审计.md` P2 calls out cross-domain direct imports as ongoing architecture debt and recommends public service/facade boundaries.
* `app/domains/playback/dedupe.py` imports `app.domains.users.auth.is_admin_user`.
* Dedupe routes use consistent `{"success": False, "msg": "需要管理员权限"}` response payloads for denied admin access.
* `app.domains.users.public_service.is_admin_user(request)` already exists and delegates to the private auth implementation.

## Assumptions

* This is a behavior-preserving refactor.
* Dedupe route URLs, response payloads, background scan scheduling, DAO calls, media-server calls, and config behavior should remain unchanged.
* This task only targets the playback dedupe auth import boundary.

## Requirements

* Update `app/domains/playback/dedupe.py` to use `app.domains.users.public_service`.
* Remove the direct `app.domains.users.auth` import from the dedupe router.
* Add focused tests that guard the import boundary.
* Add behavior tests proving representative dedupe routes use the public admin facade while preserving existing denied/admin behavior.
* Keep changes narrow.

## Acceptance Criteria

* [ ] `app/domains/playback/dedupe.py` has no import from `app.domains.users.auth`.
* [ ] Tests fail if that private import is reintroduced.
* [ ] Tests prove `get_scan_status` returns the existing denied payload through the public facade when admin is denied.
* [ ] Tests prove `get_scan_status` returns the existing scan state payload through the public facade when admin is allowed.
* [ ] Tests prove `get_dedupe_config` returns the existing config payload through the public facade when admin is allowed.
* [ ] Tests prove `save_dedupe_config` denies non-admin callers through the public facade before writing config.
* [ ] Focused tests, compile checks, import checks, private import search, and full `tests/` suite pass with the repository `uv run --with-requirements requirements.txt` command pattern.

## Definition of Done

* Code and tests are committed in one work commit.
* Completed task is archived through Trellis.
* Session journal records the work commit.

## Out of Scope

* Refactoring dedupe scan internals.
* Changing dedupe DAO behavior.
* Changing media-server delete/authentication behavior.
* Migrating other playback modules off `users.auth`.
* Changing dedupe route URLs or response shapes.

## Technical Notes

* Relevant specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/backend/error-handling.md`.
* Relevant thinking guide: `.trellis/spec/guides/cross-layer-thinking-guide.md`.
* Source audit: `docs/架构审计.md` section "P2 问题 / 跨域直接 import 仍然较多".
