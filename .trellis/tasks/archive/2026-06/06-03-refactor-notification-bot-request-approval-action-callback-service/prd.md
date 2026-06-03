# Refactor Notification Bot Request Approval Action Callback Service

## Goal

Extract the request-approval action callback handling from `app/domains/notifications/bot_service.py` into a domain-local service module. This continues `docs/架构审计.md` P2 item 5 by shrinking the notification bot large file through a behavior-preserving slice.

## Requirements

* Add a notification-domain service for request approval action callbacks:
  * `req_approve_<tmdb_id>`
  * `req_manual_<tmdb_id>`
  * `req_reject_do_<tmdb_id>_<reason_index>`
* Keep `NotificationBot._handle_callback` as the public Telegram callback entrypoint and delegate this action subset to the new service.
* Preserve legacy behavior:
  * non-action request callback data is not handled by the new service;
  * reject reason mapping stays unchanged;
  * pending rows are fetched with `media_request_dao.list_pending_requests_by_tmdb(tid)`;
  * empty pending rows clear reply markup and return handled;
  * approve still optionally calls MoviePilot subscribe when both URL and token exist;
  * moviepilot subscribe failures remain swallowed per row;
  * media request status updates preserve status codes and reject reason;
  * action text strings remain unchanged;
  * admin message record/sync behavior remains unchanged for text and caption messages.
* Preserve monkeypatch compatibility by configuring dependencies from `bot_service.py` with providers that read legacy globals dynamically.
* Add focused tests around the extracted action service boundary.

## Acceptance Criteria

* [ ] `bot_service.py` no longer contains inline approve/manual/reject action status-update branches.
* [ ] New focused tests cover approve with MoviePilot subscribe, manual status update, reject reason update, empty rows clearing markup, caption admin sync, non-action no-op, and swallowed subscribe/edit failures where practical.
* [ ] Focused tests pass.
* [ ] Import/compile checks for touched modules pass.
* [ ] Full test suite passes before the code commit.
* [ ] Work is committed separately from Trellis archive/journal commits.

## Definition of Done

* Tests added or updated for the extracted action boundary.
* Behavior remains compatible with existing notification bot callback handling.
* No new cross-domain eager import is introduced beyond existing notification-domain dependency shape.
* Trellis task is archived and session journal is recorded after code commit.

## Technical Approach

Create `app/domains/notifications/notification_bot_request_approval_action_callback_service.py` with provider-based access to `media_request_dao`, `moviepilot_client`, MoviePilot settings, Telegram client, and request admin message record/sync helpers. The service should expose `handle_request_approval_action_callback(data, cq, cid, mid, token, proxies)` and return `True` only for handled action callbacks.

`bot_service.py` should configure providers with lambdas that preserve existing runtime monkeypatch behavior and replace the remaining inline status-update branch with a service call after hdhive and menu callbacks.

## Decision (ADR-lite)

Context: request approval action handling is the largest remaining callback responsibility in `bot_service.py` after hdhive and menu branches were isolated.

Decision: extract the state-changing approve/manual/reject-do actions as one slice because they share row lookup, status update, action text, and admin message sync behavior.

Consequences: `bot_service.py` keeps only request callback dispatch ordering while the action service owns the approval mutation workflow. Broader cleanup of request admin message sync helpers remains out of scope.

## Out of Scope

* Changing hdhive plugin callback dispatch.
* Changing request approval menu callback handling.
* Changing admin message sync storage internals.
* Changing MoviePilot payload format or retry behavior.

## Technical Notes

* Architecture target: `docs/架构审计.md` P2 item 5 recommends small behavior-preserving slices for large domain files.
* Prior related task: request approval menu callbacks were extracted to `notification_bot_request_approval_menu_callback_service.py`.
* Primary remaining block: `NotificationBot._handle_callback` request approval action handling.
