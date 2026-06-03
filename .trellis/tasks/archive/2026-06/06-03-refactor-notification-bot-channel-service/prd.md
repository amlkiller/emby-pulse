# Refactor Notification Bot Channel Service

## Goal

Split Telegram channel fan-out helpers out of `app/domains/notifications/bot_service.py` into a domain-local service module while preserving existing `NotificationBot` method compatibility.

This advances `docs/架构审计.md` P2 item 5 by reducing the mixed responsibilities in the large notification bot domain file through a small behavior-preserving slice.

## Requirements

* Extract the implementation of `NotificationBot._notify_channels`, `NotificationBot._send_to_channel`, and `NotificationBot.send_to_channels` into a new `app/domains/notifications/notification_bot_channel_service.py` module.
* Keep the original `NotificationBot` methods as compatibility wrappers.
* Preserve legacy dependency/monkeypatch behavior for `bot_service.get_notify_channels`, `bot_service.get_notify_tg_bot_token`, `bot_service.get_safe_proxies`, `bot_service.telegram_client`, and `bot_service.logger`.
* Preserve current channel filtering, message/photo sending, logging, and exception swallowing behavior.
* Do not change channel configuration semantics in this slice.

## Acceptance Criteria

* [ ] New service module owns the channel fan-out implementation.
* [ ] `bot_service.py` imports and configures the new service through lazy providers.
* [ ] Existing public `NotificationBot.send_to_channels(...)` callers continue to work through the old method.
* [ ] Focused tests cover channel filtering, text/photo send behavior, and legacy monkeypatch compatibility.
* [ ] Focused tests and full test suite pass through `uv run`.
* [ ] Code/test changes are committed separately from Trellis archive and journal commits.

## Definition of Done

* Tests added or updated for the extracted boundary.
* `uv run pytest tests/ -v` passes.
* `git diff --check` passes.
* Task is archived and session journal records the work commit.

## Technical Approach

Create a small service module with `set_dependency_providers(...)` and standalone functions:

* `notify_channels(photo_io, caption, keyboard, item_type, item_info)`
* `send_to_channel(chat_id, photo_io, caption, keyboard)`
* `send_to_channels(photo_io, caption, keyboard=None)`

The original `NotificationBot` methods delegate to these functions. Providers should be lazy and return current objects/functions from `bot_service.py`, preserving tests and plugins that monkeypatch the legacy module globals.

## Out of Scope

* Fixing existing channel configuration naming or arity issues.
* Moving library new-item/new-episode notification assembly.
* Changing public notification facade behavior.
* Introducing new channel APIs or changing plugin contracts.

## Technical Notes

* Audit target: `docs/架构审计.md` P2 item 5, "domain 已迁移，但内部仍是大文件混合职责".
* Existing callers:
  * `app/domains/notifications/public_service.py`
  * `app/plugins/view_report/plugin.py`
  * internal library notification handlers in `bot_service.py`
* Existing tests around public facade:
  * `tests/test_notification_public_service_facade.py`
* Keep this as a small, behavior-preserving extraction.
