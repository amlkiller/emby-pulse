# Refactor Notification Bot Check Command Service

## Goal

Split the notification bot `/check` server status probe command out of `app/domains/notifications/bot_service.py` into a domain-local service module while preserving existing `NotificationBot` method compatibility.

This advances `docs/架构审计.md` P2 item 5 by reducing mixed responsibilities in the large notification bot domain file through a behavior-preserving slice.

## Requirements

* Extract the implementation of `NotificationBot._cmd_check` into `app/domains/notifications/notification_bot_check_command_service.py`.
* Keep the original `NotificationBot._cmd_check(cid, platform)` method as a compatibility wrapper with the same signature.
* Preserve current server info probing, media count probing, active session probing, public route latency probing, message formatting, fallback messages, and exception swallowing/logging.
* Preserve legacy dependency/monkeypatch behavior for `bot_service.media_api`, `bot_service.network_client`, `bot_service.get_media_server_public_url`, `bot_service.logger`, `bot_service.time`, and `bot.send_message`.

## Acceptance Criteria

* [ ] New service module owns the `/check` command implementation.
* [ ] `bot_service.py` imports and configures the service through lazy providers.
* [ ] Existing callers continue through `NotificationBot._cmd_check`.
* [ ] Focused tests cover online status formatting, route latency parsing for JSON and plain URL config, route failure fallback, offline fallback, route logging, and legacy monkeypatch compatibility.
* [ ] Focused tests and full test suite pass through `uv run`.
* [ ] Code/test changes are committed separately from Trellis archive and journal commits.

## Definition of Done

* Tests added or updated for the extracted boundary.
* `uv run pytest tests/ -v` passes.
* `git diff --check` passes.
* Task is archived and session journal records the work commit.

## Technical Approach

Create `notification_bot_check_command_service.py` with `set_dependency_providers(...)` and a `cmd_check(bot, cid, platform)` function. The old `NotificationBot._cmd_check` delegates to that function.

Providers should be lazy so tests and runtime monkeypatches against `bot_service` globals still work:

* `media_api_provider=lambda: media_api`
* `network_client_provider=lambda: network_client`
* `media_server_public_url_provider=lambda: get_media_server_public_url`
* `logger_provider=lambda: logger`
* `time_provider=lambda: time`

## Out of Scope

* Moving the main `_handle_message` dispatcher.
* Changing `/check` command text, thresholds, timeout values, or HTML payloads.
* Changing media server or network client implementations.
* Adding new probe behavior.

## Technical Notes

* Audit target: `docs/架构审计.md` P2 item 5.
* Current implementation lives inside `NotificationBot._cmd_check` in `app/domains/notifications/bot_service.py`.
* This task follows the same compatibility-preserving provider pattern as the recent notification bot service extractions.
