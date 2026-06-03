# Refactor Media Requests Management Router

## Goal

Continue the architecture audit P2 large-domain-file cleanup by extracting media request management and approval endpoints from `app/domains/media_requests/router.py` into a domain-local child router while preserving existing behavior.

## Requirements

* Add a new media requests domain module for request management routes.
* Move these endpoints and models out of `app/domains/media_requests/router.py`:
  * `GET /api/requests/my`
  * `GET /api/manage/requests`
  * `POST /api/manage/requests/batch`
  * `POST /api/manage/requests/action`
  * `GET /api/requests/pending_notify`
  * `AdminActionModel`
  * `BulkAdminActionModel`
* Preserve route URLs, methods, request parameters, permission checks, DAO calls, MoviePilot subscribe behavior, TMDB poster lookup behavior, notification rule checks, user bot notification calls, logging, response shapes, and exception behavior.
* Keep `app.domains.media_requests.router` compatibility exports for moved functions and models.
* Preserve existing tests that monkeypatch `media_requests.router` globals such as `list_all_requests`, `update_media_request_status`, `list_request_status_notify_items`, and `list_tg_bindings`.
* Include the new child router from `app/domains/media_requests/router.py` at the original route position after request submission and before feedback routes.
* Keep the slice narrow; do not refactor request submission, feedback, safe media, cache control, update requests, registration, or DAO internals.

## Acceptance Criteria

* [ ] `app/domains/media_requests/router.py` no longer defines the management route bodies directly.
* [ ] The moved routes remain registered through `app.domains.media_requests.router.router`.
* [ ] Moved functions and models remain importable from `app.domains.media_requests.router`.
* [ ] Route ordering remains stable around discovery, submit, management, feedback, safe media, and cache control.
* [ ] Existing monkeypatch-based tests continue to pass through provider wiring.
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

Create `app/domains/media_requests/management_router.py` with its own `APIRouter`, move the request management routes and their two Pydantic models there, then import the moved names and child router back into `media_requests/router.py`. Use dependency providers for user auth, DAO functions, MoviePilot settings/client, TMDB client/proxy, notification rule owner, notification service, logger, and `safe_error_message` so old-module monkeypatch compatibility remains intact.

## Decision (ADR-lite)

**Context**: `media_requests/router.py` still mixes request submission, user/admin request management, feedback, safe media, update requests, and registration.

**Decision**: Extract only cohesive request management endpoints in this slice using the established child-router plus provider bridge pattern.

**Consequences**: The main router gets smaller without behavior changes. Provider wiring stays explicit to preserve direct-call and monkeypatch compatibility during incremental decomposition.

## Out of Scope

* Changing approval/status workflow behavior.
* Changing notification payloads, rule names, channels, or user bot calls.
* Refactoring request submission or update request routes.
* Refactoring feedback, safe media, cache control, registration, or DAO internals.
* Introducing a new service layer.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Existing child-router pattern: media request auth, discovery, feedback, safe media, and cache control routers preserve old compatibility exports via imports and dependency providers.
* Existing tests monkeypatch old router globals; provider lambdas from `media_requests.router` must resolve those globals at call time.
