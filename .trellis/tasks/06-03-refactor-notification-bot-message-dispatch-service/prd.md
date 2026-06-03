# Refactor Notification Bot Message Dispatch Service

## Goal

Continue the architecture-audit refactor by extracting the notification bot message dispatch and admin-check logic from the large `bot_service.py` file into a domain-local service module. Preserve all command routing behavior and legacy `NotificationBot` entry points.

## Requirements

* Add a notification-domain module for bot message dispatch.
* Move `_handle_message()` routing behavior into the new module.
* Move `_is_admin()` behavior into the new module.
* Keep `NotificationBot._handle_message()` and `_is_admin()` as compatibility wrappers.
* Preserve reply-mode precedence before command parsing.
* Preserve command matching order, including `/check` before other shorter commands and `/emby_restart` before non-command fallback.
* Preserve non-admin non-command warning behavior.
* Preserve admin non-command event publication to `bot.admin_message`.
* Use lazy providers for `get_tg_chat_id`, event bus, and logger so legacy monkeypatches on `bot_service` remain effective.

## Acceptance Criteria

* [ ] `bot_service.py` line count is reduced by moving dispatch/admin-check implementation into a new domain-local module.
* [ ] Existing command dispatch invokes the same legacy command wrapper methods.
* [ ] Reply-mode messages still call `_handle_msg_reply_message()` before command routing.
* [ ] Telegram admin checks preserve comma and Chinese-comma parsing.
* [ ] WeCom admin checks still allow messages.
* [ ] Non-admin non-command text logs a warning and does not publish.
* [ ] Admin non-command text logs and publishes `bot.admin_message`.
* [ ] Focused notification bot dispatch tests pass.
* [ ] Full test suite passes before the code commit.

## Definition of Done

* Tests added or updated for the extracted dispatch boundary.
* Focused compile/import verification passes.
* Focused tests and full tests pass through `uv run`.
* Work commit is separate from Trellis archive and journal commits.

## Technical Approach

Create `app/domains/notifications/notification_bot_message_dispatch_service.py` with `is_admin(bot, cid, platform)` and `handle_message(bot, text, cid, platform)`. Configure providers from `bot_service.py` for `get_tg_chat_id`, `bus`, and `logger`. Keep `NotificationBot` methods as thin wrappers to preserve existing external and test entry points.

## Decision (ADR-lite)

**Context**: `bot_service.py` still owns command dispatch, command wrappers, polling, callback handling, lifecycle, and cross-domain notifications.

**Decision**: Extract only message dispatch and admin-check logic in this slice. Leave command implementations, polling, and callback handling unchanged.

**Consequences**: The command routing responsibility becomes independently testable while avoiding changes to command services or Telegram polling behavior.

## Out of Scope

* Changing command behavior or dispatch ordering.
* Changing Telegram command registration.
* Refactoring callback handling.
* Refactoring polling lifecycle.
* Changing event bus semantics.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Current target: `app/domains/notifications/bot_service.py`.
* Existing pattern: extracted notification bot services preserve legacy `NotificationBot` wrappers and use lazy dependency providers for monkeypatch compatibility.
