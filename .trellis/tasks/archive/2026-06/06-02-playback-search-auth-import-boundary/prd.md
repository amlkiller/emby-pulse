# playback search auth import boundary

## Goal

Remove the unused private users auth import from the playback search router.

## What I already know

* `docs/架构审计.md` P2 calls out cross-domain direct imports as ongoing architecture debt and recommends public service/facade boundaries.
* `app/domains/playback/search.py` imports `app.domains.users.auth.is_admin_user`.
* The imported admin helper is not used in `search.py`; the module uses `require_login` for the image route and a session-user check for library search.

## Assumptions

* This is a behavior-preserving import-boundary cleanup.
* Search route URLs, response payloads, login checks, media-server calls, and pinyin matching behavior should remain unchanged.
* This task only targets the playback search private auth import.

## Requirements

* Remove the direct `app.domains.users.auth` import from `app/domains/playback/search.py`.
* Do not add a replacement users facade import unless behavior actually needs it.
* Add focused tests that guard the import boundary.
* Add a small behavior test proving the existing unauthenticated library search response remains unchanged.
* Keep changes narrow.

## Acceptance Criteria

* [ ] `app/domains/playback/search.py` has no import from `app.domains.users.auth`.
* [ ] Tests fail if that private import is reintroduced.
* [ ] Tests prove `global_library_search` still returns `{"status": "error", "message": "未登录"}` for unauthenticated requests before touching media-server dependencies.
* [ ] Focused tests, compile checks, import checks, private import search, and full `tests/` suite pass with the repository `uv run --with-requirements requirements.txt` command pattern.

## Definition of Done

* Code and tests are committed in one work commit.
* Completed task is archived through Trellis.
* Session journal records the work commit.

## Out of Scope

* Refactoring search logic or media-server calls.
* Changing `require_login` usage.
* Migrating other playback modules off `users.auth`.
* Changing search route URLs or response shapes.

## Technical Notes

* Relevant specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/backend/error-handling.md`.
* Relevant thinking guide: `.trellis/spec/guides/cross-layer-thinking-guide.md`.
* Source audit: `docs/架构审计.md` section "P2 问题 / 跨域直接 import 仍然较多".
