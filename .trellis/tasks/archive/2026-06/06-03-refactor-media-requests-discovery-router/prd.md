# Refactor Media Requests Discovery Router

## Goal

Continue the architecture audit P2 large-domain-file cleanup by extracting media request discovery and browsing endpoints from `app/domains/media_requests/router.py` into a domain-local child router while preserving existing behavior.

## Requirements

* Add a new media requests domain module for discovery/browse routes.
* Move these endpoints out of `app/domains/media_requests/router.py`:
  * `GET /api/requests/item_info`
  * `GET /api/requests/hub_data`
  * `GET /api/requests/search`
  * `GET /api/requests/trending`
  * `GET /api/requests/tv/{tmdb_id}`
  * `GET /api/requests/check/{media_type}/{tmdb_id}`
* Preserve route URLs, methods, request parameters, permission checks, session/account-deleted behavior, cache keys and TTLs, Emby/TMDB calls, proxy handling, logging, response shapes, and exception behavior.
* Keep `app.domains.media_requests.router` compatibility exports for the moved route functions.
* Keep helper functions importable from `app.domains.media_requests.router` where current code uses them:
  * `get_tmdb_season_info`
  * `get_emby_admin`
  * `check_emby_exists`
* Preserve existing route ordering: auth routes first, discovery routes before request submission, feedback/safe/cache-control/update routes after request management.
* Keep the slice narrow; do not refactor request submission, request management, feedback, safe media, cache control, update requests, registration, or `community_cache_service.py`.

## Acceptance Criteria

* [ ] `app/domains/media_requests/router.py` no longer defines the discovery route bodies directly.
* [ ] The moved routes remain registered through `app.domains.media_requests.router.router`.
* [ ] Moved functions remain importable from `app.domains.media_requests.router`.
* [ ] Route ordering remains stable around auth, discovery, submit, and later child routers.
* [ ] Focused compile/import/route checks pass.
* [ ] Relevant media request router boundary tests pass.
* [ ] The full test suite passes before commit.

## Definition of Done

* Tests added or updated where useful to lock route inclusion and compatibility exports.
* Compile/import checks pass for changed modules.
* `git diff --check` passes.
* No spec update is needed unless the work discovers a new project convention or gotcha.
* Code changes are committed before task archive and journal bookkeeping.

## Technical Approach

Create `app/domains/media_requests/discovery_router.py` with its own `APIRouter`, move the discovery routes and their local helpers there, then import the moved names and child router back into `media_requests/router.py`. Use dependency providers for `user_service`, `media_api`, `tmdb_client`, cache helpers, cache TTL, `get_safe_proxies`, `safe_error_message`, `logger`, `_check_user_exists`, and settings helpers so old-module monkeypatch compatibility remains intact.

## Decision (ADR-lite)

**Context**: `media_requests/router.py` still mixes discovery/browsing, request submission, request management, update requests, feedback, cache control, and registration.

**Decision**: Extract only cohesive discovery/browse endpoints in this slice using the established child-router plus provider bridge pattern.

**Consequences**: The main router gets smaller without behavior changes. Provider wiring remains explicit but protects direct-call and monkeypatch compatibility during incremental decomposition.

## Out of Scope

* Changing discovery ranking, filtering, cache keys, TTLs, or external API parameters.
* Refactoring request submission or request management endpoints.
* Refactoring update request, registration, feedback, safe media, or cache control routes.
* Refactoring `community_cache_service.py`.
* Introducing a new service layer.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Existing child-router pattern: media request auth, feedback, safe media, and cache control routers preserve old compatibility exports via imports and dependency providers.
* Current frontend callers use the same `/api/requests/*` URLs; URLs and response shapes must remain stable.
