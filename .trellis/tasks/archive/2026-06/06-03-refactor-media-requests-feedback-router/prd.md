# Refactor Media Requests Feedback Router

## Goal

Continue the architecture audit P2 large-domain-file cleanup by extracting the media request feedback endpoints from `app/domains/media_requests/router.py` into a domain-local child router while preserving existing behavior.

## Requirements

* Add a new media requests domain module for feedback routes.
* Move these endpoints out of `app/domains/media_requests/router.py`:
  * `POST /api/requests/feedback/submit`
  * `GET /api/requests/feedback/my`
  * `GET /api/manage/feedback`
  * `POST /api/manage/feedback/action`
  * `POST /api/manage/feedback/batch`
* Move `FeedbackSubmitModel`, `FeedbackActionModel`, and `BulkFeedbackActionModel` with the route group.
* Preserve route URLs, methods, permission checks, session checks, response shapes, poster fallback behavior, DAO calls, notification rule lookup, photo/web notification behavior, logging, and exception handling.
* Keep `app.domains.media_requests.router` compatibility exports for moved endpoint functions and models.
* Preserve existing tests that monkeypatch `app.domains.media_requests.router` globals and call moved functions directly.
* Include the new child router from `app/domains/media_requests/router.py` at the original route position between pending notify and safe media routes.
* Keep the slice narrow; do not refactor request submission, admin request actions, safe media browsing, cache refresh, update requests, or registration routes.

## Acceptance Criteria

* [ ] `app/domains/media_requests/router.py` no longer defines the feedback route bodies directly.
* [ ] The five moved routes remain registered through `app.domains.media_requests.router.router`.
* [ ] Moved functions and request models remain importable from `app.domains.media_requests.router`.
* [ ] Existing feedback notification and admin feedback tests keep passing through the compatibility exports.
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

Create `app/domains/media_requests/feedback_router.py` with its own `APIRouter`, move the feedback request models and endpoint functions there, then import the moved names and child router back into `media_requests/router.py`. Use dependency providers for user admin checks, account-existence checks, DAO functions, notification services, settings readers, constants, and logger access so old-module monkeypatch compatibility remains intact.

## Decision (ADR-lite)

**Context**: `media_requests/router.py` still mixes browsing, submissions, admin workflows, feedback, cache refresh, update requests, and registration. Feedback is a cohesive route group with a clear model set and already has focused tests around notification behavior.

**Decision**: Extract only the feedback route group in this slice, using the child-router plus provider bridge pattern already used for recent users and media request auth splits.

**Consequences**: The main router gets smaller without behavior changes. Provider wiring remains verbose, but it protects direct-call and monkeypatch compatibility during incremental decomposition.

## Out of Scope

* Changing feedback notification semantics or notification rule fallback behavior.
* Changing feedback status values or response payloads.
* Refactoring request submission, admin request actions, safe media browsing, cache refresh, update requests, or registration flows.
* Introducing a new feedback service layer.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Existing large-file cleanup pattern: domain child routers preserve old compatibility exports via imports and dependency providers.
* Existing regression coverage: `tests/test_media_requests_router_notification_rule_facade_boundary.py::test_submit_feedback_uses_public_rule_before_notifications` and `tests/test_media_requests_router_public_auth_facade_boundary.py::test_get_all_feedback_allows_admin_through_public_facade`.
