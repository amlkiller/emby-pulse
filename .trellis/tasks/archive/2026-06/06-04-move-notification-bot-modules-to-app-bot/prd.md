# Move Notification Bot Modules To App Bot

## Goal

Move bot implementation modules out of `app/domains/notifications/` into the top-level `app/bot/` package and update Python imports so the application continues to load the same bot admin API, DAO behavior, and Telegram user bot behavior from the new package locations.

## Requirements

* Move `bot.py` to `app/bot/bot.py`.
* Move `bot_admin_dao.py` to `app/bot/bot_admin_dao.py`.
* Move `user_bot_*.py` modules to `app/bot/user_bot/`.
* Update all imports that reference the old `app.domains.notifications` module paths.
* Preserve existing runtime behavior and public route definitions.
* Do not refactor unrelated notification modules.

## Acceptance Criteria

* [x] `app/domains/notifications/bot.py` no longer exists.
* [x] `app/domains/notifications/bot_admin_dao.py` no longer exists.
* [x] New files exist under `app/bot/`.
* [x] `app/domains/notifications/user_bot_*.py` no longer exists.
* [x] User bot files exist under `app/bot/user_bot/`.
* [x] No source import references remain for `app.domains.notifications.bot` or `app.domains.notifications.bot_admin_dao`.
* [x] No source import references remain for `app.domains.notifications.user_bot_*`.
* [x] Project import/type validation passes through the repo's configured Python command.

## Definition of Done

* Code paths are updated consistently.
* Lint/type/import checks are run where practical.
* No behavior changes beyond module relocation.

## Technical Approach

Use direct package moves: preserve file contents, update intra-module imports from the old domain path to `app.bot` / `app.bot.user_bot`, then run search and Python validation to catch missed references.

## Decision (ADR-lite)

**Context**: The repo already has an `app/bot/` package containing bot-related services, while bot admin and Telegram user bot implementation modules still lived under `app/domains/notifications/`.

**Decision**: Move the admin bot modules to `app/bot/` root and move Telegram user bot modules to `app/bot/user_bot/`, matching the user's requested target path.

**Consequences**: Existing code should import admin bot API/DAO modules from `app.bot` and Telegram user bot modules from `app.bot.user_bot`. Notification-domain services remain untouched unless they directly reference the moved modules.

## Out of Scope

* Renaming functions, routes, services, or database tables.
* Reorganizing `app/bot/notification_bot/`.

## Technical Notes

* Existing `app/bot/__init__.py` is empty.
* Existing search found the old DAO import in `app/domains/notifications/bot.py`.
* `app/bot/notification_bot/bot_service.py` already imports elsewhere from the bot package tree and is not part of this move.
