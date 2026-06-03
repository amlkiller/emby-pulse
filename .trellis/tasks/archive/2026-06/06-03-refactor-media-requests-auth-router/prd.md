# Refactor Media Requests Auth Router

## Goal

Continue the architecture audit P2 cleanup by extracting the user community authentication routes from `app/domains/media_requests/router.py` into a domain-local child router while preserving existing behavior and compatibility imports.

## Requirements

* Add a new media requests domain module for user community auth routes.
* Move these routes out of `app/domains/media_requests/router.py`:
  * `POST /api/requests/auth`
  * `GET /api/requests/check`
  * `POST /api/requests/logout`
* Move `RequestLoginModel` with the route group.
* Preserve route URLs, methods, session mutations, response shapes, host-port rejection, media server calls, DAO calls, passwordless-user rejection, expired/disabled-account behavior, route URL selection, and logout session clearing.
* Keep `app.domains.media_requests.router` compatibility exports for `RequestLoginModel`, `request_system_login`, `check_auth`, and `request_system_logout`.
* Preserve existing tests that monkeypatch `app.domains.media_requests.router` globals and call moved functions directly.
* Keep the slice narrow; do not refactor request submission, feedback, registration, cache refresh, or update-request routes.

## Acceptance Criteria

* [ ] `app/domains/media_requests/router.py` no longer defines the three user community auth route bodies directly.
* [ ] The three moved routes remain registered through `app.domains.media_requests.router.router`.
* [ ] Moved functions and request model remain importable from `app.domains.media_requests.router`.
* [ ] Existing passwordless-login regression test keeps passing through the compatibility export.
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

Create `app/domains/media_requests/auth_router.py` with its own `APIRouter`, move `RequestLoginModel`, `request_system_login`, `check_auth`, and `request_system_logout` there, then import the moved names and child router back into `media_requests/router.py`. Use dependency providers for media API, settings readers, DAO functions, and `_check_user_exists` so old-module monkeypatch compatibility remains intact.

## Decision (ADR-lite)

**Context**: `media_requests/router.py` is still one of the largest domain files and mixes user community auth, browsing, request submission, feedback, cache services, update requests, and registration.

**Decision**: Extract only the user community authentication route group in this slice, using the same child-router plus provider bridge pattern already used for recent users router splits.

**Consequences**: This reduces the large router without changing behavior. The provider bridge keeps compatibility a little verbose, but avoids breaking existing direct function calls and monkeypatch-based tests during incremental decomposition.

## Out of Scope

* Changing authentication semantics or password validation behavior.
* Changing session key names or response payloads.
* Refactoring media request submission, feedback, registration, cache refresh, or update-request flows.
* Introducing a new cross-domain auth service.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Existing large-file cleanup pattern: child routers under `app/domains/users/` preserve old compatibility exports via imports and dependency providers.
* Existing regression coverage: `tests/test_regression_fixes.py::test_request_login_rejects_passwordless_emby_users` calls `app.domains.media_requests.router.request_system_login` directly and monkeypatches old-module globals.
