# Refactor Media Requests Safe Media Router

## Goal

Continue the architecture audit P2 large-domain-file cleanup by extracting the user-visible safe media list endpoints from `app/domains/media_requests/router.py` into a domain-local child router while preserving existing behavior.

## Requirements

* Add a new media requests domain module for safe media routes.
* Move these endpoints out of `app/domains/media_requests/router.py`:
  * `GET /api/requests/safe_top`
  * `GET /api/requests/safe_latest`
* Preserve route URLs, methods, request parameters, session checks, account-deleted behavior, cache reads/writes, playback stats calls, Emby permission filtering, logging, response shapes, and exception behavior.
* Keep `app.domains.media_requests.router` compatibility exports for `get_safe_top_media` and `get_safe_latest`.
* Preserve existing tests that inspect route ordering and direct-call compatibility.
* Include the new child router from `app/domains/media_requests/router.py` at the original route position between feedback routes and cache control routes.
* Keep the slice narrow; do not refactor hub/search/trending, request submission, update requests, registration, or `community_cache_service.py` internals.

## Acceptance Criteria

* [ ] `app/domains/media_requests/router.py` no longer defines the safe media route bodies directly.
* [ ] The two moved routes remain registered through `app.domains.media_requests.router.router`.
* [ ] Moved functions remain importable from `app.domains.media_requests.router`.
* [ ] Route ordering remains stable around feedback, safe media, cache control, and update-request routes.
* [ ] Focused compile/import/route checks pass.
* [ ] Relevant media request router tests pass.
* [ ] The full test suite passes before commit.

## Definition of Done

* Tests added or updated where useful to lock route inclusion and compatibility exports.
* Compile/import checks pass for changed modules.
* `git diff --check` passes.
* No spec update is needed unless the work discovers a new project convention or gotcha.
* Code changes are committed before task archive and journal bookkeeping.

## Technical Approach

Create `app/domains/media_requests/safe_media_router.py` with its own `APIRouter`, move `get_safe_top_media` and `get_safe_latest` there, then import the moved names and child router back into `media_requests/router.py`. Use dependency providers for `_check_user_exists`, cache helpers, TTL constants, `playback_stats`, `media_api`, `logger`, and `safe_error_message` so old-module monkeypatch compatibility remains intact.

## Decision (ADR-lite)

**Context**: `media_requests/router.py` still mixes user browsing, request management, safe media lists, update requests, and registration. Safe media routes are cohesive and depend mainly on cache helpers, playback stats, and Emby permission filtering.

**Decision**: Extract only `safe_top` and `safe_latest` in this slice using the established child-router plus provider bridge pattern.

**Consequences**: The main router gets smaller without behavior changes. Provider wiring remains explicit but protects direct-call and monkeypatch compatibility during incremental decomposition.

## Out of Scope

* Changing safe media ranking, limits, cache keys, TTLs, or permission filtering behavior.
* Refactoring `community_cache_service.py`.
* Refactoring hub/search/trending, request submission, update requests, or registration.
* Introducing a new service layer.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Existing child-router pattern: media request auth, feedback, and cache control routers preserve old compatibility exports via imports and dependency providers.
* Current frontend callers: `static/js/request_app.js` fetches `/api/requests/safe_latest` and `/api/requests/safe_top`.
