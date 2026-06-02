# Media Requests Playback Stats Public Facade Boundary

## Goal

Move playback stats calls in `app/domains/media_requests/router.py` off the private playback stats router module and through the playback public facade, preserving existing user community top/latest media and cache refresh behavior.

## Requirements

- Add narrow public facade wrappers in `app/domains/playback/public_service.py` for:
  - `api_latest_media(request=None, limit=60)`
  - `api_top_movies(request=None, user_id=None, category="all", sort_by="count", exclude_types=None, period="all")`
- Replace local `app.domains.playback.stats` imports in `media_requests/router.py` with calls through the playback public facade.
- Preserve response payloads, cache keys, cache TTLs, permission filtering, error behavior, and logging.
- Keep this task scoped to the media requests playback stats boundary and focused regression tests.

## Acceptance Criteria

- [ ] `media_requests/router.py` has no direct `app.domains.playback.stats` import.
- [ ] `playback.public_service.api_latest_media()` delegates to the existing playback stats implementation.
- [ ] `playback.public_service.api_top_movies()` delegates to the existing playback stats implementation.
- [ ] `get_safe_top_media()` uses `router.playback_service.api_top_movies(...)`.
- [ ] `get_safe_latest()` uses `router.playback_service.api_latest_media(...)`.
- [ ] `_refresh_community_cache()` uses playback public facade calls for both latest and top cache refresh.
- [ ] Focused boundary tests pass.
- [ ] Compile, import, private-import scan, and full pytest suite pass before commit.

## Definition of Done

- Tests added/updated for public facade delegation and media requests router import/call boundary.
- Python verification commands use `uv run`.
- Work commit is created for code/test files, followed by separate Trellis archive and journal commits.

## Technical Approach

Expose thin lazy wrappers from `app.domains.playback.public_service` to the existing `app.domains.playback.stats` functions. Import that facade in `media_requests/router.py` as `playback_service`, remove local `playback.stats` imports, and call `playback_service.api_latest_media(...)` / `playback_service.api_top_movies(...)` in the existing code paths.

## Out of Scope

- No changes to playback stats query logic, media API filtering, cache structure, route URLs, response shapes, or user community UI behavior.
- No migration of other playback private imports outside `media_requests/router.py`.
- No split of `media_requests/router.py` or `playback/stats.py`.

## Technical Notes

- Audit source: `docs/架构审计.md` P2 issue 6, cross-domain private import cleanup.
- Existing playback facade: `app/domains/playback/public_service.py`.
- Target files inspected:
  - `app/domains/media_requests/router.py`
  - `app/domains/playback/public_service.py`
  - `tests/test_playback_public_service_facade.py`
  - `tests/test_media_requests_router_public_auth_facade_boundary.py`
