# Move Notification Bot Modules

## Goal

Move notification bot implementation modules from `app/domains/notifications/` into `app/bot/notification_bot/` and update code references so imports continue to resolve without changing notification bot behavior.

## Requirements

* Create `app/bot/notification_bot/` as the new home for notification bot service modules.
* Move every current `notification_bot_*.py` file from `app/domains/notifications/` into the new folder.
* Move `app/domains/notifications/bot_service.py` and `app/domains/notifications/bot_service_dao.py` into the same new folder.
* Update production and test imports/references from `app.domains.notifications.notification_bot_*` to the new package path.
* Keep notification bot service behavior-compatible while pointing it at the moved modules and DAO.
* Do not move unrelated notification, user bot, DAO, router, or public service modules.

## Acceptance Criteria

* [ ] No notification bot implementation files remain directly under `app/domains/notifications/`.
* [ ] `app/bot/notification_bot/` contains the moved modules and is importable as a Python package.
* [ ] Repository search finds no stale `app.domains.notifications.notification_bot_*` imports in production or tests.
* [ ] Focused compile/import verification passes through `uv run`.

## Definition of Done

* Code references are updated.
* Focused quality checks pass, or any skipped/failing verification is reported with the exact command.
* No unrelated behavior or dependency changes are introduced.

## Technical Approach

Use a behavior-preserving package move. Update direct import paths and package-level imports; avoid compatibility re-export shims unless tests reveal existing dynamic import contracts that require them.

## Out of Scope

* Renaming individual service modules.
* Moving `bot.py`, non-bot notification DAOs, routers, or user bot modules.
* Changing notification bot behavior, provider wiring, callbacks, or command handling.

## Technical Notes

* Initial scan found 40 `notification_bot_*.py` files under `app/domains/notifications/`.
* `app/bot` did not initially exist and must be created.
* Relevant specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`.
