# Refactor Notification Bot Command Registration Service

## Goal

Continue the architecture-audit refactor by extracting Telegram bot command registration from the large `bot_service.py` file into a focused notification-domain service module. Preserve the command list and legacy `NotificationBot._set_commands()` entry point.

## Requirements

* Add a notification-domain module responsible for registering Telegram bot commands.
* Move `_set_commands()` implementation into the new module.
* Keep `NotificationBot._set_commands()` as a compatibility wrapper.
* Preserve the exact command list, command order, descriptions, Telegram API method, proxy usage, timeout, and silent failure behavior.
* Preserve lazy providers for `get_notify_tg_bot_token`, `get_safe_proxies`, and `telegram_client` so legacy monkeypatches on `bot_service` remain effective.
* Add focused boundary tests through the legacy `NotificationBot._set_commands()` method.

## Acceptance Criteria

* [ ] `bot_service.py` line count is reduced by moving command registration into a new domain-local module.
* [ ] No Telegram API call is made when the bot token is missing.
* [ ] The same 13 commands are registered in the same order when a token exists.
* [ ] Registration calls `telegram_client.post_api(token, "setMyCommands", json={"commands": ...}, proxies=get_safe_proxies(), timeout=10)`.
* [ ] Exceptions from command registration remain silently swallowed.
* [ ] Focused command-registration tests pass.
* [ ] Full test suite passes before code commit.

## Definition of Done

* Tests added or updated for the extracted command registration boundary.
* Focused compile/import verification passes.
* Focused tests and full tests pass through `uv run`.
* Work commit is separate from Trellis archive and journal commits.

## Technical Approach

Create `app/domains/notifications/notification_bot_command_registration_service.py` with `set_commands()`. Configure dependency providers from `bot_service.py` for token lookup, safe proxy lookup, and Telegram client. Keep `NotificationBot._set_commands()` as a thin wrapper.

## Decision (ADR-lite)

**Context**: `bot_service.py` still contains startup orchestration, Telegram polling, callback handling, and several small bot responsibilities.

**Decision**: Extract only Telegram command registration in this slice. Do not change startup flow or polling lifecycle.

**Consequences**: A small startup responsibility becomes independently testable while keeping runtime behavior unchanged.

## Out of Scope

* Changing Telegram command descriptions or ordering.
* Changing bot startup flow.
* Refactoring polling or callback handling.
* Refactoring user bot command registration.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Current target: `app/domains/notifications/bot_service.py`.
* Existing pattern: notification bot services use lazy dependency providers and legacy `NotificationBot` wrappers for compatibility.
