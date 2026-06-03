# Refactor Notification Bot User Login Service

## Goal

Continue the architecture-audit refactor by extracting `NotificationBot.on_user_login()` from the large `bot_service.py` file into a focused notification-domain service module. Preserve notification rule checks, legacy fallback behavior, message formatting, user mute checks, avatar fallback, channel fan-out, web notification persistence, logging, and the legacy `NotificationBot.on_user_login()` entry point.

## Requirements

* Add a notification-domain module responsible for notification bot user-login handling.
* Move `on_user_login()` implementation into the new module.
* Keep `NotificationBot.on_user_login()` as a compatibility wrapper.
* Preserve the initial notification rule check:
  * Try `get_notify_rule("user_login")`.
  * Return when no rule exists or `enabled` is false.
  * Fall back to `get_notify_user_login()` when rule lookup fails.
* Preserve payload extraction for `User`, `Session`, `UserId`, `Title`, `UserName`, `RemoteEndPoint`, `Client`, `AppName`, and `DeviceName`.
* Preserve `bot._is_muted(user_id, "login")` behavior and mute logging.
* Preserve IP location lookup, login message text, and timestamp format.
* Preserve per-channel behavior:
  * Send photo to Telegram/WeCom when `tg_bot` or `wecom` is enabled.
  * Use downloaded avatar when available, otherwise DiceBear fallback URL with URL-quoted username.
  * Use platform `all`, `tg`, or `wecom` according to enabled channels.
  * Add web notification when `web` is enabled.
* Preserve channel-send failure fallback: log `[用户登录通知] 发送失败: ...` and send using the old `platform="all"` photo behavior.
* Preserve outer assembly failure logging: `登录通知组装异常: ...`.
* Use lazy providers for `get_notify_rule`, `get_notify_user_login`, `get_location`, `add_system_notification`, `datetime`, `urllib.parse.quote`, and `logger` so legacy monkeypatches and runtime state remain effective.

## Acceptance Criteria

* [ ] `bot_service.py` line count is reduced by moving user-login handling into a new domain-local module.
* [ ] `NotificationBot.on_user_login()` delegates to the new service.
* [ ] Disabled or missing notification rules skip login notifications unless the legacy fallback setting is used after lookup failure.
* [ ] Mute checks prevent sends and log the existing mute message.
* [ ] Telegram/WeCom channel selection and avatar fallback behavior are preserved.
* [ ] Web channel persistence uses the existing type, title, message, and action URL.
* [ ] Channel-send failures log and fall back to all-platform photo sending.
* [ ] Outer assembly failures are logged and swallowed.
* [ ] Focused user-login tests pass.
* [ ] Full test suite passes before code commit.

## Definition of Done

* Tests added or updated for the extracted user-login boundary.
* Focused compile/import verification passes.
* Focused tests and full tests pass through `uv run`.
* Work commit is separate from Trellis archive and journal commits.

## Technical Approach

Create `app/domains/notifications/notification_bot_user_login_service.py` with `handle_user_login(bot, data)`. Configure providers from `bot_service.py` for rule lookup, legacy setting lookup, location lookup, web notification persistence, time/URL helpers, and logger. Keep `NotificationBot.on_user_login()` as a thin wrapper.

## Decision (ADR-lite)

**Context**: `bot_service.py` still contains several event handlers with notification formatting and side effects mixed into the bot class.

**Decision**: Extract only user-login notification handling in this slice, keeping event subscription names and delivery APIs unchanged.

**Consequences**: Login notification behavior becomes independently testable and `bot_service.py` shrinks without changing risk, playback, library, deletion, or daily report handlers.

## Out of Scope

* Changing login notification copy, icons, HTML, or timestamp format.
* Changing notification rule storage or channel semantics.
* Changing event bus subscription names.
* Refactoring item deletion, playback, library, or daily report handlers.
* Introducing a shared notification event abstraction.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Current target: `app/domains/notifications/bot_service.py`.
* Existing extraction pattern: notification bot named service modules with lazy dependency providers and legacy wrappers.
