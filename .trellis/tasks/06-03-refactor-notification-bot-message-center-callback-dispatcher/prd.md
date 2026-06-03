# Refactor Notification Bot Message Center Callback Dispatcher

## Goal

Move the remaining Telegram message-center callback dispatch branches out of `app/domains/notifications/bot_service.py` and into the existing domain-local `notification_bot_message_center_callback_service.py`. This continues `docs/架构审计.md` P2 item 5 by shrinking the notification bot large file through a small behavior-preserving slice.

## Requirements

* Add a service-level dispatcher for message-center callback data:
  * `msg_reply:<user_id>`
  * `msg_block:<user_id>`
  * `msg_cancel:<user_id>`
  * `msg_unblock:<user_id>`
* Keep `NotificationBot._handle_callback` as the public Telegram callback entrypoint and delegate the message-center callback group to the service.
* Preserve existing `NotificationBot` compatibility wrappers:
  * `_handle_msg_reply_callback`
  * `_handle_msg_block_callback`
  * `_handle_msg_unblock_callback`
  * `_handle_msg_reply_message`
* Preserve legacy behavior:
  * non-`msg_` callback data is not handled by the new dispatcher;
  * `msg_reply`, `msg_block`, and `msg_unblock` continue to call the same service helper behavior;
  * `msg_cancel` discards `cid` from `bot._msg_reply_mode`;
  * `msg_cancel` edits the Telegram message to `❌ 已取消回复` and clears inline keyboard;
  * Telegram edit failures during `msg_cancel` are swallowed;
  * dependency providers continue reading legacy `bot_service` globals dynamically.
* Add focused tests for the new dispatcher/cancel boundary.

## Acceptance Criteria

* [ ] `bot_service.py` no longer contains inline `msg_reply`, `msg_block`, `msg_cancel`, or `msg_unblock` dispatch branches.
* [ ] Existing helper wrapper methods remain callable.
* [ ] New focused tests cover reply/block/unblock dispatch routing, cancel behavior, non-message callback no-op, and swallowed cancel edit failures.
* [ ] Focused tests pass.
* [ ] Import/compile checks for touched modules pass.
* [ ] Full test suite passes before the code commit.
* [ ] Work is committed separately from Trellis archive/journal commits.

## Definition of Done

* Tests added or updated for the extracted dispatcher boundary.
* Behavior remains compatible with existing notification bot callback handling.
* No new cross-domain eager import is introduced.
* Trellis task is archived and session journal is recorded after code commit.

## Technical Approach

Extend `notification_bot_message_center_callback_service.py` with `handle_message_center_callback(bot, data, cid, mid, token, proxies, cq)`. The dispatcher should parse callback prefixes and call the existing service helpers. Move the `msg_cancel` inline behavior into a focused service helper or branch in the dispatcher, using the existing Telegram client provider.

`bot_service.py` should configure no new dependency shape beyond the existing message-center service providers, then replace the inline message-center branch group with one dispatcher call.

## Decision (ADR-lite)

Context: the earlier message-center callback service extraction moved helper implementations but deliberately left the main `_handle_callback` dispatcher in `bot_service.py`. After several other callback extractions, the remaining inline dispatch branches are now isolated and safe to move.

Decision: reuse the existing message-center callback service rather than creating another module, because the moved responsibility is still message-center callback dispatch.

Consequences: `bot_service.py` loses another callback group while the existing service becomes the owner of both helper implementation and dispatch selection for message-center callback data.

## Out of Scope

* Refactoring request approval `req_` callbacks.
* Changing message DAO behavior.
* Changing callback data formats, Telegram payload text, or keyboards.
* Removing existing `NotificationBot` wrapper methods.

## Technical Notes

* Architecture target: `docs/架构审计.md` P2 item 5 recommends small behavior-preserving slices for large domain files.
* Prior related task: `.trellis/tasks/archive/2026-06/06-03-refactor-notification-bot-message-center-callback-service`.
* Primary files: `app/domains/notifications/bot_service.py`, `app/domains/notifications/notification_bot_message_center_callback_service.py`, and `tests/test_notification_bot_message_center_callback_service_boundary.py`.
