# Refactor Notification Bot Emby Restart Command Service

## Goal

Split the notification bot `/emby_restart` command and matching `emby_restart:*` callback implementation out of `app/domains/notifications/bot_service.py` into a domain-local service module while preserving existing `NotificationBot` method compatibility.

This advances `docs/架构审计.md` P2 item 5 by reducing mixed responsibilities in the large notification bot domain file through a behavior-preserving slice.

## Requirements

* Extract the implementation of these `NotificationBot` behaviors into `app/domains/notifications/notification_bot_emby_restart_command_service.py`:
  * `_cmd_emby_restart`
  * `emby_restart:*` callback handling currently embedded in `_handle_callback`
* Keep original `NotificationBot._cmd_emby_restart(cid, text, platform)` as a compatibility wrapper with the same signature.
* Keep `_handle_callback` as the callback dispatcher, delegating the `emby_restart:*` branch to the new service.
* Preserve current plugin lookup/config lookup, enabled checks, server list rendering, inline keyboard payloads, restart-all behavior, single-server restart behavior, error messages, and logging.
* Preserve legacy dependency/monkeypatch behavior for `bot_service.logger`, dynamically imported `app.plugins.get_plugin_config`, `app.plugins.get_plugin`, and `bot.send_message`.

## Acceptance Criteria

* [ ] New service module owns the `/emby_restart` command implementation and the `emby_restart:*` callback implementation.
* [ ] `bot_service.py` imports and configures the service through lazy providers.
* [ ] Existing callers continue through old `NotificationBot._cmd_emby_restart` and `_handle_callback`.
* [ ] Focused tests cover disabled plugin, empty server config, server list keyboard, restart-all callback, single-server callback success/failure, invalid server index, and callback exception logging/failure message.
* [ ] Focused tests and full test suite pass through `uv run`.
* [ ] Code/test changes are committed separately from Trellis archive and journal commits.

## Definition of Done

* Tests added or updated for the extracted boundary.
* `uv run pytest tests/ -v` passes.
* `git diff --check` passes.
* Task is archived and session journal records the work commit.

## Technical Approach

Create `notification_bot_emby_restart_command_service.py` with `set_dependency_providers(...)` and functions that accept the `NotificationBot` instance when send wrappers are needed:

* `cmd_emby_restart(bot, cid, text, platform)`
* `handle_emby_restart_callback(bot, data, cid, cq, platform="tg")`

Providers should be lazy so tests and runtime monkeypatches against `bot_service` globals still work:

* `logger_provider=lambda: logger`
* `get_plugin_provider` and `get_plugin_config_provider` configured through callables that dynamically import `app.plugins` when invoked.

## Out of Scope

* Moving the main `_handle_callback` dispatcher.
* Changing `/emby_restart` command syntax.
* Changing callback data formats, message text, inline keyboard layout, or plugin API usage.
* Changing the Emby restart plugin implementation.

## Technical Notes

* Audit target: `docs/架构审计.md` P2 item 5.
* Current command implementation lives in `NotificationBot._cmd_emby_restart`.
* Current callback implementation lives inside the `if data.startswith("emby_restart:")` branch of `NotificationBot._handle_callback`.
* This task follows the same compatibility-preserving provider pattern as the recent notification bot service extractions.
