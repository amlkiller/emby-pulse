# Refactor Media Requests Registration Router

## Goal

Continue the architecture audit P2 large-domain-file cleanup by extracting the public media request registration endpoint from `app/domains/media_requests/router.py` into a domain-local child router while preserving existing behavior.

## Requirements

* Add a new media requests domain module for registration routes.
* Move these items out of `app/domains/media_requests/router.py`:
  * `POST /api/requests/register`
  * `UserRegisterModel`
  * `_restore_invitation_code`
* Preserve route URL, method, request model, username/password validation, invitation claim/rollback behavior, Emby user creation, policy/template application, metadata persistence, cache invalidation, session auto-login, notification rule checks, welcome message behavior, response shapes, and exception behavior.
* Keep `app.domains.media_requests.router` compatibility exports for `UserRegisterModel`, `_restore_invitation_code`, and `user_community_register`.
* Preserve existing tests that monkeypatch old-module globals such as `media_api`, `claim_registration_invitation`, `save_registered_user_meta`, `get_media_server_welcome_message`, `notify_admin`, and `notification_service`.
* Include the new child router from `app/domains/media_requests/router.py` at the original route position after update routes.
* Keep the slice narrow; do not refactor request submission, management, feedback, safe media, cache control, update requests, or DAO internals.

## Acceptance Criteria

* [ ] `app/domains/media_requests/router.py` no longer defines the registration route body directly.
* [ ] The registration route remains registered through `app.domains.media_requests.router.router`.
* [ ] Moved model/helper/function remain importable from `app.domains.media_requests.router`.
* [ ] Route ordering remains stable with registration after update routes.
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

Create `app/domains/media_requests/registration_router.py` with its own `APIRouter`, move the registration model, helper, and endpoint there, then import the moved names and child router back into `media_requests/router.py`. Use dependency providers for validation, media API, invitation DAO helpers, users public service, notification rule owner, notification service, system notification writer, media server settings, logger, and safe error mapping so old-module monkeypatch compatibility remains intact.

## Decision (ADR-lite)

**Context**: `media_requests/router.py` still mixes submission, update requests, registration, and compatibility wiring.

**Decision**: Extract only the public registration endpoint in this slice using the established child-router plus provider bridge pattern.

**Consequences**: The main router gets smaller without behavior changes. Provider wiring remains explicit but protects direct-call and monkeypatch compatibility during incremental decomposition.

## Out of Scope

* Changing registration validation rules.
* Changing invitation consumption or rollback semantics.
* Changing Emby user policy/template behavior.
* Changing notification payloads, rule names, channels, or welcome message behavior.
* Refactoring request submission, management, update request routes, or DAO internals.
* Introducing a new service layer.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Existing child-router pattern: media request auth, discovery, management, feedback, safe media, and cache control routers preserve old compatibility exports via imports and dependency providers.
* Existing registration tests monkeypatch old router globals; provider lambdas from `media_requests.router` must resolve those globals at call time.
