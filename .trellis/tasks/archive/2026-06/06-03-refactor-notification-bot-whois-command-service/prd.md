# Refactor Notification Bot Whois Command Service

## Goal

Split the notification bot `/whois` command formatting and query handling out of `app/domains/notifications/bot_service.py` into a domain-local service module while preserving existing `NotificationBot` method compatibility.

This advances `docs/架构审计.md` P2 item 5 by reducing mixed responsibilities in the large notification bot domain file through a behavior-preserving slice.

## Requirements

* Extract the implementation of these `NotificationBot` helpers into `app/domains/notifications/notification_bot_whois_command_service.py`:
  * `_format_expire_status`
  * `_format_whois_row`
  * `_cmd_whois`
* Keep original `NotificationBot` methods as compatibility wrappers with the same signatures.
* Preserve existing `/whois` usage validation, result formatting, HTML escaping, DAO lookup behavior, logging, and sent messages.
* Preserve legacy dependency/monkeypatch behavior for `bot_service.user_bot_dao`, `bot_service.escape_html`, and `bot_service.logger`.

## Acceptance Criteria

* [ ] New service module owns the `/whois` command implementation.
* [ ] `bot_service.py` imports and configures the service through lazy providers.
* [ ] Existing callers continue through old `NotificationBot` method names.
* [ ] Focused tests cover empty/missing keyword handling, no-match output, single/multiple result formatting, expire-date formatting, exception logging, and legacy monkeypatch compatibility.
* [ ] Focused tests and full test suite pass through `uv run`.
* [ ] Code/test changes are committed separately from Trellis archive and journal commits.

## Definition of Done

* Tests added or updated for the extracted boundary.
* `uv run pytest tests/ -v` passes.
* `git diff --check` passes.
* Task is archived and session journal records the work commit.

## Technical Approach

Create `notification_bot_whois_command_service.py` with `set_dependency_providers(...)` and functions that accept the `NotificationBot` instance when send wrappers or existing helper compatibility are needed:

* `format_expire_status(expire_date)`
* `format_whois_row(row, index=None)`
* `cmd_whois(bot, cid, text, platform)`

The old `NotificationBot` methods delegate to these functions. Providers should be lazy so tests and runtime monkeypatches against `bot_service` globals still work.

## Out of Scope

* Moving the main `_handle_message` dispatcher.
* Changing `/whois` command syntax or search normalization.
* Changing HTML payloads, labels, emoji, or ordering of formatted fields.
* Changing user bot DAO query implementation.

## Technical Notes

* Audit target: `docs/架构审计.md` P2 item 5.
* Current implementation lives near the bottom of `NotificationBot` in `app/domains/notifications/bot_service.py`.
* This task follows the same compatibility-preserving provider pattern as the recent notification bot service extractions.
