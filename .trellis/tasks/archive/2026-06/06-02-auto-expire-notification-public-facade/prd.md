# auto expire notification public facade boundary

## Goal

Move the built-in auto-expire plugin off private notification user-bot internals so user reminder delivery goes through `app.domains.notifications.public_service`.

## What I already know

* `docs/架构审计.md` P2 calls out plugins directly importing domain internals as ongoing architecture debt and recommends public service/facade boundaries.
* `app/plugins/auto_expire/plugin.py` imports `app.domains.notifications.user_bot_service.user_bot` and private `_send` inside `_send_user_remind`.
* `app/domains/notifications/public_service.py` already exists for cross-domain notification callers, but it currently exposes admin bot operations only.
* The plugin already uses `app.domains.users.public_service` for user lookups and auth checks.

## Assumptions

* This is a behavior-preserving refactor. The plugin should still skip reminders when the user bot is not running, still look up the Telegram chat id through the users facade, and still send the same reminder text when possible.
* Notification domain internals may keep using `user_bot_service` directly; this task targets the built-in plugin as an external caller.

## Requirements

* Add a narrow public notification facade for the user-bot operations `auto_expire` needs.
* Update `app/plugins/auto_expire/plugin.py` so it no longer imports `app.domains.notifications.user_bot_service`.
* Add focused tests for the new public facade delegation.
* Add an import-boundary test that fails if `auto_expire` reintroduces private notification user-bot imports.
* Keep changes narrow; do not refactor other notification or plugin call sites in this task.

## Acceptance Criteria

* [ ] `app/plugins/auto_expire/plugin.py` has no import from `app.domains.notifications.user_bot_service`.
* [ ] `app/domains/notifications/public_service.py` exposes the needed user-bot behavior without requiring plugin callers to import `_send` or `user_bot`.
* [ ] Tests cover user-bot running-state delegation and send delegation.
* [ ] Tests cover the `auto_expire` plugin reminder path through the public facade.
* [ ] Focused tests, compile checks, and full `tests/` suite pass with the repository `uv run --with-requirements requirements.txt` command pattern.

## Definition of Done

* Code and tests are committed in one work commit.
* Completed task is archived through Trellis.
* Session journal records the work commit.

## Out of Scope

* Refactoring notification domain-internal uses of `user_bot_service`.
* Refactoring media request or risk notification call sites.
* Changing message text, plugin scheduling, or user lookup behavior.

## Technical Notes

* Relevant specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/backend/error-handling.md`.
* Relevant thinking guide: `.trellis/spec/guides/cross-layer-thinking-guide.md`.
* Source audit: `docs/架构审计.md` section "P2 问题 / 跨域直接 import 仍然较多".
