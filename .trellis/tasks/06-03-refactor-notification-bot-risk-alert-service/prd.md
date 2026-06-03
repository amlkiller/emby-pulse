# Refactor Notification Bot Risk Alert Service

## Goal

Continue the architecture-audit refactor by extracting `NotificationBot.on_risk_alert()` from the large `bot_service.py` file into a focused notification-domain service module. Preserve message formatting, action button behavior, system notification persistence, logging, and the legacy `NotificationBot.on_risk_alert()` entry point.

## Requirements

* Add a notification-domain module responsible for notification bot risk alert handling.
* Move `on_risk_alert()` implementation into the new module.
* Keep `NotificationBot.on_risk_alert()` as a compatibility wrapper.
* Preserve risk payload defaults for `user_id`, `username`, `current`, `limit`, `devices_info`, and `violation_action`.
* Preserve the existing `violation_action` label mapping and default label.
* Preserve the ban button behavior: include the ban callback only when a user id exists and the action is not `auto_ban`.
* Preserve risk dashboard URL fallback from `get_pulse_url()` to `get_media_server_main_public_or_host()`.
* Preserve `send_message("sys_notify", msg, reply_markup=..., platform="all")`.
* Preserve best-effort `add_system_notification(...)` behavior and error logging.
* Use lazy providers for `get_pulse_url`, `get_media_server_main_public_or_host`, `add_system_notification`, and `logger` so legacy monkeypatches on `bot_service` remain effective.

## Acceptance Criteria

* [ ] `bot_service.py` line count is reduced by moving risk alert handling into a new domain-local module.
* [ ] `NotificationBot.on_risk_alert()` delegates to the new service.
* [ ] Risk alert messages preserve the existing title, user/current/limit/device/action text, and platform.
* [ ] Ban button is present only for actionable user ids and omitted for `auto_ban`.
* [ ] Risk dashboard URL uses `get_pulse_url()` first and falls back to `get_media_server_main_public_or_host()`.
* [ ] System notification persistence uses the existing `notify_type`, title, message, and action URL.
* [ ] Persistence exceptions are swallowed after logging through the current legacy logger.
* [ ] Focused risk alert tests pass.
* [ ] Full test suite passes before code commit.

## Definition of Done

* Tests added or updated for the extracted risk alert boundary.
* Focused compile/import verification passes.
* Focused tests and full tests pass through `uv run`.
* Work commit is separate from Trellis archive and journal commits.

## Technical Approach

Create `app/domains/notifications/notification_bot_risk_alert_service.py` with `handle_risk_alert(bot, data)`. Configure providers from `bot_service.py` for URL fallback, system notification persistence, and logger. Keep `NotificationBot.on_risk_alert()` as a thin wrapper.

## Decision (ADR-lite)

**Context**: `bot_service.py` still contains event subscription wrappers, notification event handlers, callback handling, and compatibility methods.

**Decision**: Extract only the wind-risk alert event handler in this slice. Keep message rendering and side effects behavior-preserving, and leave playback/library/login/deletion handlers for later slices.

**Consequences**: Risk alert behavior becomes independently testable and `bot_service.py` shrinks without changing event subscription names or callback dispatch.

## Out of Scope

* Changing risk alert copy, icons, HTML, or callback data.
* Changing risk service behavior.
* Changing event bus subscription names.
* Refactoring playback, library, login, or deletion notification handlers.
* Introducing a shared notification event abstraction.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Current target: `app/domains/notifications/bot_service.py`.
* Existing extraction pattern: notification bot named service modules with lazy dependency providers and legacy wrappers.
