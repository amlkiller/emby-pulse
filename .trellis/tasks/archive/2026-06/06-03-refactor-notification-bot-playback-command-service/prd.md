# Refactor Notification Bot Playback Command Service

## Goal

Split the notification bot `/now` and `/recent` playback query commands out of `app/domains/notifications/bot_service.py` into a domain-local service module while preserving existing `NotificationBot` method compatibility.

This advances `docs/架构审计.md` P2 item 5 by reducing mixed responsibilities in the large notification bot domain file through a behavior-preserving slice.

## Requirements

* Extract the implementation of these `NotificationBot` helpers into `app/domains/notifications/notification_bot_playback_command_service.py`:
  * `_cmd_now`
  * `_cmd_recent`
* Keep original `NotificationBot` methods as compatibility wrappers with the same signatures.
* Preserve current Emby session lookup, playback history SQL query, progress bar formatting, username lookup, sent messages, and fallback messages.
* Preserve legacy dependency/monkeypatch behavior for `bot_service.media_api`, `bot_service.playback_store`, and `bot._get_username` / `bot.send_message`.

## Acceptance Criteria

* [ ] New service module owns the `/now` and `/recent` command implementations.
* [ ] `bot_service.py` imports and configures the service through lazy providers.
* [ ] Existing callers continue through old `NotificationBot._cmd_now` and `NotificationBot._cmd_recent`.
* [ ] Focused tests cover active playback formatting, no-active-session fallback, connection failure fallback, recent playback formatting, no-history fallback, query failure fallback, and legacy monkeypatch compatibility.
* [ ] Focused tests and full test suite pass through `uv run`.
* [ ] Code/test changes are committed separately from Trellis archive and journal commits.

## Definition of Done

* Tests added or updated for the extracted boundary.
* `uv run pytest tests/ -v` passes.
* `git diff --check` passes.
* Task is archived and session journal records the work commit.

## Technical Approach

Create `notification_bot_playback_command_service.py` with `set_dependency_providers(...)` and functions that accept the `NotificationBot` instance when send wrappers or username helper compatibility are needed:

* `cmd_now(bot, cid, platform)`
* `cmd_recent(bot, cid, platform)`

Providers should be lazy so tests and runtime monkeypatches against `bot_service` globals still work:

* `media_api_provider=lambda: media_api`
* `playback_store_provider=lambda: playback_store`

## Out of Scope

* Moving the main `_handle_message` dispatcher.
* Changing `/now` or `/recent` command syntax.
* Changing message text, progress bar thresholds, SQL query shape, or username lookup behavior.
* Moving playback event notification logic or `_format_ticks`.

## Technical Notes

* Audit target: `docs/架构审计.md` P2 item 5.
* Current implementation lives inside `NotificationBot._cmd_now` and `NotificationBot._cmd_recent` in `app/domains/notifications/bot_service.py`.
* This task follows the same compatibility-preserving provider pattern as the recent notification bot service extractions.
