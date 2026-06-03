# Refactor Media Requests Cache Control Router

## Goal

Continue the architecture audit P2 large-domain-file cleanup by extracting media request community cache control endpoints and lifecycle wrappers from `app/domains/media_requests/router.py` into a domain-local module while preserving existing behavior.

## Requirements

* Add a new media requests domain module for community cache control routes and lifecycle wrappers.
* Move these endpoints out of `app/domains/media_requests/router.py`:
  * `POST /api/requests/refresh_cache`
  * `POST /api/requests/clear_cache`
* Move these lifecycle wrapper functions out of the main router body:
  * `start_community_cache_refresh_loop`
  * `stop_community_cache_refresh_loop`
  * `start_media_request_services`
* Preserve route URLs, methods, `JSONResponse` status codes, admin/session checks, response payloads, cache refresh/clear behavior, schema bootstrap call, refresh-loop state sync, and bootstrap import compatibility.
* Keep `app.domains.media_requests.router` compatibility exports for the moved endpoint and lifecycle functions.
* Preserve existing tests that monkeypatch `app.domains.media_requests.router` globals and call moved functions directly.
* Include the new child router from `app/domains/media_requests/router.py` at the original route position between safe media routes and update-request routes.
* Keep the slice narrow; do not refactor safe media browsing, update requests, registration, or `community_cache_service.py` internals.

## Acceptance Criteria

* [ ] `app/domains/media_requests/router.py` no longer defines the cache control endpoint bodies or lifecycle wrapper bodies directly.
* [ ] The two moved routes remain registered through `app.domains.media_requests.router.router`.
* [ ] Moved functions remain importable from `app.domains.media_requests.router`.
* [ ] Bootstrap imports from `app.domains.media_requests.router` keep working.
* [ ] Existing lifecycle and admin-denial tests keep passing through compatibility exports.
* [ ] Focused compile/import/route checks pass.
* [ ] Relevant media request router and lifecycle tests pass.
* [ ] The full test suite passes before commit.

## Definition of Done

* Tests added or updated where useful to lock route inclusion and compatibility exports.
* Compile/import checks pass for changed modules.
* `git diff --check` passes.
* No spec update is needed unless the work discovers a new project convention or gotcha.
* Code changes are committed before task archive and journal bookkeeping.

## Technical Approach

Create `app/domains/media_requests/cache_control_router.py` with its own `APIRouter`, move the cache refresh/clear endpoints and lifecycle wrapper functions there, then import the moved names and child router back into `media_requests/router.py`. Use dependency providers for `community_cache_service`, `_refresh_community_cache`, `_invalidate_cache`, `_sync_community_cache_task_state`, `ensure_media_request_schema`, and `user_service` so old-module monkeypatch compatibility remains intact.

## Decision (ADR-lite)

**Context**: `media_requests/router.py` still owns HTTP endpoints, background cache lifecycle wrappers, update-request workflows, and registration. The cache control group is already backed by `community_cache_service.py`, making it a small behavior-preserving extraction candidate.

**Decision**: Extract only cache control endpoints and lifecycle wrappers in this slice, keeping `community_cache_service.py` unchanged and preserving old `media_requests.router` exports.

**Consequences**: The main router gets smaller and cache lifecycle ownership becomes clearer. Provider wiring keeps compatibility verbose but protects bootstrap imports and direct monkeypatch-based tests during incremental decomposition.

## Out of Scope

* Changing cache TTLs, refresh cadence, refresh thread behavior, or cache data shape.
* Refactoring safe media browsing or `community_cache_service.py` internals.
* Changing bootstrap service registration.
* Changing update-request or registration routes.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Existing lifecycle coverage: `tests/test_bootstrap_long_loop_stop_hooks.py::test_media_request_refresh_loop_stop_resets_state_and_allows_restart`.
* Existing admin API coverage: `tests/test_media_requests_router_public_auth_facade_boundary.py::test_refresh_cache_denies_non_admin_before_refresh`.
* Bootstrap currently imports `start_media_request_services` and `stop_community_cache_refresh_loop` from `app.domains.media_requests.router`; compatibility exports must remain.
