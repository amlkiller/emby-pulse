# Refactor Notification Bot Polling Service

## Goal

Continue the architecture-audit refactor by extracting the `NotificationBot` Telegram polling loop from the large `bot_service.py` file into a focused notification-domain service module. Preserve polling behavior, filtering, offset updates, message dispatch, callback submission, retry waits, and legacy `NotificationBot._polling_loop()` entry point.

## Requirements

* Add a notification-domain module responsible for `NotificationBot` Telegram polling.
* Move `_polling_loop()` implementation into the new module.
* Keep `NotificationBot._polling_loop()` as a compatibility wrapper.
* Preserve token lookup, admin chat-id whitelist parsing, group/channel skip behavior, message/caption extraction, text-link URL appending, callback whitelist checks, callback async submission, offset updates, timeout values, proxy usage, and stop-event retry waits.
* Use lazy providers for `get_notify_tg_bot_token`, `get_tg_chat_id`, `get_safe_proxies`, `telegram_client`, and `_submit_bot_task` so legacy monkeypatches on `bot_service` remain effective.
* Add focused boundary tests through the legacy `NotificationBot._polling_loop()` method.

## Acceptance Criteria

* [ ] `bot_service.py` line count is reduced by moving polling implementation into a new domain-local module.
* [ ] Polling uses `telegram_client.get_updates(token, params={"offset": bot.offset, "timeout": 30}, proxies=get_safe_proxies(), timeout=35)`.
* [ ] Each processed update advances `bot.offset` to `update_id + 1`.
* [ ] Group, supergroup, channel, and non-admin private messages are ignored.
* [ ] Text/caption messages append `text_link` URLs from `entities` and `caption_entities` before calling `_handle_message(..., platform="tg")`.
* [ ] Admin callback queries are submitted via `_submit_bot_task(bot._handle_callback, cq)`.
* [ ] Non-200 and exception branches use `bot._stop_event.wait(5)` and return when the stop event is set.
* [ ] Focused polling tests pass.
* [ ] Full test suite passes before code commit.

## Definition of Done

* Tests added or updated for the extracted polling boundary.
* Focused compile/import verification passes.
* Focused tests and full tests pass through `uv run`.
* Work commit is separate from Trellis archive and journal commits.

## Technical Approach

Create `app/domains/notifications/notification_bot_polling_service.py` with `run_polling_loop(bot)`. Configure providers from `bot_service.py` for token lookup, admin chat-id lookup, safe proxy lookup, Telegram client, and bot task submission. Keep `NotificationBot._polling_loop()` as a thin wrapper.

## Decision (ADR-lite)

**Context**: `bot_service.py` still owns polling, callback handling, notification event handlers, and several compatibility wrappers.

**Decision**: Extract only the Telegram polling loop in this slice, following the existing `user_bot_polling_service.py` pattern while preserving the notification bot's admin filtering and message parsing behavior.

**Consequences**: Polling becomes independently testable and the large file shrinks without changing callback handling or startup lifecycle.

## Out of Scope

* Changing polling retry intervals.
* Changing callback handling.
* Changing message command dispatch.
* Changing bot startup/stop lifecycle.
* Refactoring user bot polling.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Current target: `app/domains/notifications/bot_service.py`.
* Existing similar pattern: `app/domains/notifications/user_bot_polling_service.py`.
