# Refactor Notification Bot Delivery Service

## Goal

Split notification delivery entrypoints out of `app/domains/notifications/bot_service.py` into a domain-local service module while preserving existing `NotificationBot` method compatibility.

This advances `docs/架构审计.md` P2 item 5 by reducing mixed responsibilities in the large notification bot domain file through a behavior-preserving slice.

## Requirements

* Extract the implementation of these `NotificationBot` methods into a new `app/domains/notifications/notification_bot_delivery_service.py` module:
  * `send_photo`
  * `send_message`
  * `edit_message`
* Keep the original `NotificationBot` methods as compatibility wrappers with the same signatures.
* Preserve legacy dependency/monkeypatch behavior for `bot_service` globals including `network_client`, `telegram_client`, `_submit_bot_task`, token/settings helpers, proxy helpers, and `logger`.
* Preserve current Telegram multi-chat fan-out, photo URL download fallback, photo-to-text fallback, WeCom task submission, reply markup JSON serialization, and exception swallowing behavior.
* Do not move polling, callback handling, command handling, or message assembly in this slice.

## Acceptance Criteria

* [ ] New service module owns the send/edit delivery implementation.
* [ ] `bot_service.py` imports and configures the new service through lazy providers.
* [ ] Existing `NotificationBot.send_photo`, `send_message`, and `edit_message` callers continue through old methods.
* [ ] Focused tests cover Telegram photo send, fallback to text, multi-chat message fan-out, WeCom task submission, and legacy monkeypatch compatibility.
* [ ] Focused tests and full test suite pass through `uv run`.
* [ ] Code/test changes are committed separately from Trellis archive and journal commits.

## Definition of Done

* Tests added or updated for the extracted boundary.
* `uv run pytest tests/ -v` passes.
* `git diff --check` passes.
* Task is archived and session journal records the work commit.

## Technical Approach

Create a service module with `set_dependency_providers(...)` and functions:

* `send_photo(bot, chat_id, photo_io, caption, parse_mode="HTML", reply_markup=None, platform="all", wecom_photo_io=None)`
* `send_message(bot, chat_id, text, parse_mode="HTML", reply_markup=None, platform="all")`
* `edit_message(bot, chat_id, message_id, text, parse_mode="HTML", reply_markup=None, platform="tg")`

The functions accept the `NotificationBot` instance so WeCom calls still invoke `bot._send_wecom_photo` / `bot._send_wecom_message`, preserving class-level monkeypatch compatibility. Providers should be lazy and read current objects/functions from `bot_service.py` at call time.

## Out of Scope

* Moving WeCom helper implementation again.
* Moving Telegram polling or callback handling.
* Moving command handlers.
* Changing public notification facade behavior.
* Changing message payload formats or retry behavior.

## Technical Notes

* Audit target: `docs/架构审计.md` P2 item 5, "domain 已迁移，但内部仍是大文件混合职责".
* Existing public facade delegates to the `NotificationBot` methods, so wrapper signatures must remain stable.
* Keep this as a small, behavior-preserving extraction.
