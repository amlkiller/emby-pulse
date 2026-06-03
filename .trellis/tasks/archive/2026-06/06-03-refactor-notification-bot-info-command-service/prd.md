# Refactor Notification Bot Info Command Service

## Goal

Continue the architecture-audit refactor by extracting a small, behavior-preserving command slice from the large notification bot domain file. Move `/calendar` and `/help` command handling out of `app/domains/notifications/bot_service.py` into a domain-local command service while keeping legacy `NotificationBot` entry points.

## Requirements

* Add a notification-domain module for bot information commands.
* Move `/calendar` command implementation into the new module.
* Move `/help` command message construction/sending into the new module.
* Keep `NotificationBot._cmd_calendar()` and `NotificationBot._cmd_help()` as compatibility wrappers.
* Preserve lazy lookup behavior for calendar notify functions and logger so monkeypatches on legacy `bot_service` globals remain effective.
* Preserve exact user-facing messages and failure logging behavior.
* Add focused boundary tests through the legacy `NotificationBot` methods.

## Acceptance Criteria

* [ ] `bot_service.py` line count is reduced by moving calendar/help implementation into a new domain-local module.
* [ ] Existing dispatch from `_handle_message()` continues to call the same legacy wrapper methods.
* [ ] `/calendar` sends the formatted calendar update on success.
* [ ] `/calendar` logs `[Bot] calendar error: ...` and sends `❌ 获取今日更新失败` on failure.
* [ ] `/help` sends the same help menu content through `send_message`.
* [ ] Focused notification bot info command tests pass.
* [ ] Full test suite passes before code commit.

## Definition of Done

* Tests added or updated for the extracted command boundary.
* Focused compile/import verification passes.
* Focused tests and full tests pass through `uv run`.
* Work commit is separate from Trellis archive and journal commits.

## Technical Approach

Create `app/domains/notifications/notification_bot_info_command_service.py` with `cmd_calendar(bot, cid, platform)` and `cmd_help(bot, cid, platform)`. Configure lazy providers from `bot_service.py` for `get_today_updates`, `format_notify_message`, and `logger`, so tests or callers patching legacy `bot_service` globals still affect the extracted implementation. Keep `NotificationBot._cmd_calendar()` and `_cmd_help()` as thin wrappers.

## Decision (ADR-lite)

**Context**: `bot_service.py` remains one of the largest domain files even after previous command extractions.

**Decision**: Extract only small information commands in this slice. Keep dispatch, polling, callback handling, and message center behavior unchanged.

**Consequences**: The large file shrinks modestly while another cohesive command responsibility becomes independently testable. Larger lifecycle/callback areas remain for later slices.

## Out of Scope

* Changing Telegram command registration.
* Changing `_handle_message()` dispatch ordering.
* Refactoring calendar notify service internals.
* Refactoring Telegram polling or callback handling.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Current target: `app/domains/notifications/bot_service.py`.
* Existing pattern: command service modules keep lazy providers and legacy `NotificationBot` wrappers for compatibility.
