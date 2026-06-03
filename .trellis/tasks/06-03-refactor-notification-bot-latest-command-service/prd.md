# Refactor Notification Bot Latest Command Service

## Goal

Split the notification bot `/latest` command implementation out of `app/domains/notifications/bot_service.py` into a domain-local service module while preserving the existing `NotificationBot` method compatibility.

This advances `docs/架构审计.md` P2 item 5 by reducing mixed responsibilities in the large notification bot domain file through a behavior-preserving slice.

## Requirements

* Extract the implementation of `NotificationBot._cmd_latest` into `app/domains/notifications/notification_bot_latest_command_service.py`.
* Keep original `NotificationBot._cmd_latest(cid, platform)` as a compatibility wrapper with the same signature.
* Preserve current admin user lookup, Emby latest-items request path/params/timeout, status handling, message text, item formatting, date fallback, type icons, logging, and failure messages.
* Preserve legacy dependency/monkeypatch behavior for `bot_service.media_api`, `bot_service.get_admin_id`, `bot_service.logger`, and `bot.send_message`.

## Acceptance Criteria

* [ ] New service module owns the `/latest` command implementation.
* [ ] `bot_service.py` imports and configures the service through lazy providers.
* [ ] Existing callers continue through old `NotificationBot._cmd_latest`.
* [ ] Focused tests cover missing admin ID, non-200 latest query, empty latest list, movie/episode formatting, missing dates, and exception logging/failure message.
* [ ] Focused tests and full test suite pass through `uv run`.
* [ ] Code/test changes are committed separately from Trellis archive and journal commits.

## Definition of Done

* Tests added or updated for the extracted boundary.
* `uv run pytest tests/ -v` passes.
* `git diff --check` passes.
* Task is archived and session journal records the work commit.

## Technical Approach

Create `notification_bot_latest_command_service.py` with `set_dependency_providers(...)` and a function that accepts the `NotificationBot` instance when send wrappers are needed:

* `cmd_latest(bot, cid, platform)`

Providers should be lazy so tests and runtime monkeypatches against `bot_service` globals still work:

* `media_api_provider=lambda: media_api`
* `admin_id_provider=lambda: get_admin_id`
* `logger_provider=lambda: logger`

## Out of Scope

* Changing `/latest` command syntax.
* Changing the Emby API endpoint, request params, limits, messages, or formatting.
* Moving `_cmd_search`, `_cmd_stats`, or media-quality helpers in this slice.

## Technical Notes

* Audit target: `docs/架构审计.md` P2 item 5.
* Current command implementation lives in `NotificationBot._cmd_latest`.
* This task follows the same compatibility-preserving provider pattern as recent notification bot command service extractions.
