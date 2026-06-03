# Refactor Notification Bot Message Center Callback Service

## Goal

Split message-center callback helpers out of `app/domains/notifications/bot_service.py` into a domain-local service module while preserving existing `NotificationBot` method compatibility.

This advances `docs/架构审计.md` P2 item 5 by reducing mixed responsibilities in the large notification bot domain file through a behavior-preserving slice.

## Requirements

* Extract the implementation of these `NotificationBot` helpers into `app/domains/notifications/notification_bot_message_center_callback_service.py`:
  * `_handle_msg_reply_callback`
  * `_handle_msg_block_callback`
  * `_handle_msg_unblock_callback`
  * `_handle_msg_reply_message`
* Keep original `NotificationBot` methods as compatibility wrappers with the same signatures.
* Preserve `NotificationBot._msg_reply_mode` behavior.
* Preserve legacy dependency/monkeypatch behavior for `bot_service.message_dao`, `bot_service.telegram_client`, `bot_service.media_api`, and `bot_service.logger`.
* Preserve current callback payloads, reply keyboards, confirmation messages, exception swallowing/logging, and return values.

## Acceptance Criteria

* [ ] New service module owns the message-center callback helper implementation.
* [ ] `bot_service.py` imports and configures the service through lazy providers.
* [ ] Existing helper callers continue through old `NotificationBot` method names.
* [ ] Focused tests cover reply-mode setup, block/unblock callback edits, reply-message conversation creation, and legacy monkeypatch compatibility.
* [ ] Focused tests and full test suite pass through `uv run`.
* [ ] Code/test changes are committed separately from Trellis archive and journal commits.

## Definition of Done

* Tests added or updated for the extracted boundary.
* `uv run pytest tests/ -v` passes.
* `git diff --check` passes.
* Task is archived and session journal records the work commit.

## Technical Approach

Create `notification_bot_message_center_callback_service.py` with `set_dependency_providers(...)` and functions that accept the `NotificationBot` instance when reply-mode state or send wrappers are needed:

* `handle_msg_reply_callback(bot, cid, mid, user_id, token, proxies)`
* `handle_msg_block_callback(cid, mid, user_id, token, proxies, cq)`
* `handle_msg_unblock_callback(cid, mid, user_id, token, proxies, cq)`
* `handle_msg_reply_message(bot, text, cid)`

The old `NotificationBot` methods delegate to these functions. Providers should be lazy so tests and runtime monkeypatches against `bot_service` globals still work.

## Out of Scope

* Moving the main `_handle_callback` dispatcher.
* Moving message center DAO code.
* Changing callback data formats or Telegram payloads.
* Changing user-bot reply delivery behavior.

## Technical Notes

* Audit target: `docs/架构审计.md` P2 item 5.
* `_handle_msg_reply_message` dynamically imports `app.domains.notifications.messages._send_bot_reply_to_user`; preserve this behavior.
