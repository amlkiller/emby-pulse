# Refactor Notification Bot Request Approval Menu Callback Service

## Goal

Extract the request-approval menu callback handling from `app/domains/notifications/bot_service.py` into a domain-local service module. This continues `docs/架构审计.md` P2 item 5 by shrinking the notification bot large file through a behavior-preserving slice.

## Requirements

* Add a notification-domain service for request approval menu callbacks:
  * `req_reject_menu_<tmdb_id>`
  * `req_back_<tmdb_id>`
* Keep `NotificationBot._handle_callback` as the public Telegram callback entrypoint and delegate this menu subset to the new service.
* Preserve legacy behavior:
  * non-menu request callback data is not handled by the new service;
  * `req_reject_menu_*` renders the same reject-reason keyboard;
  * `req_back_*` renders the same approval keyboard;
  * `req_back_*` keeps the same hdhive-enabled detection behavior and fallback keyboard;
  * `req_back_*` keeps `get_pulse_url() or "http://127.0.0.1:10307"` fallback behavior;
  * Telegram `editMessageReplyMarkup` failures are swallowed.
* Preserve monkeypatch compatibility by configuring dependencies from `bot_service.py` with providers that read legacy globals dynamically.
* Add focused tests around the extracted menu service boundary.

## Acceptance Criteria

* [ ] `bot_service.py` no longer contains inline `req_reject_menu_*` or `req_back_*` keyboard-building branches.
* [ ] New focused tests cover reject menu, back menu with hdhive enabled and summary row, back menu fallback without hdhive, non-menu no-op, and swallowed Telegram edit failures.
* [ ] Focused tests pass.
* [ ] Import/compile checks for touched modules pass.
* [ ] Full test suite passes before the code commit.
* [ ] Work is committed separately from Trellis archive/journal commits.

## Definition of Done

* Tests added or updated for the extracted request menu boundary.
* Behavior remains compatible with existing notification bot callback handling.
* No new cross-domain eager import is introduced.
* Trellis task is archived and session journal is recorded after code commit.

## Technical Approach

Create `app/domains/notifications/notification_bot_request_approval_menu_callback_service.py` with provider-based access to `telegram_client`, `media_request_dao`, `get_pulse_url`, and `get_plugin`. The service should expose `handle_request_approval_menu_callback(data, cid, mid, token, proxies)` and return `True` only for handled menu callbacks.

`bot_service.py` should configure providers with lambdas that preserve existing runtime monkeypatch behavior and replace the inline `reject menu` / `back` branches with a service call before the remaining request approval status-update logic.

## Decision (ADR-lite)

Context: the request approval callback block is the largest remaining inline callback branch in `bot_service.py`, but the full approve/manual/reject flow is too large for one safe slice.

Decision: extract only menu-rendering callbacks first. These callbacks only edit Telegram reply markup and do not mutate media request status.

Consequences: `bot_service.py` loses another request-callback responsibility while the state-changing request approval flow remains in place for later focused extraction.

## Out of Scope

* Extracting approve/manual/reject status updates.
* Changing MoviePilot subscription behavior.
* Changing hdhive plugin callback dispatch.
* Changing request admin message sync behavior.

## Technical Notes

* Architecture target: `docs/架构审计.md` P2 item 5 recommends small behavior-preserving slices for large domain files.
* Primary remaining block: `NotificationBot._handle_callback` request approval handling.
* Existing provider-based callback service examples: feedback, risk ban, message center callback services.
