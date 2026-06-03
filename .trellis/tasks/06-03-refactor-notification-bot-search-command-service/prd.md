# Refactor Notification Bot Search Command Service

## Goal

Split the notification bot `/search` command implementation and its local media technical-info formatter out of `app/domains/notifications/bot_service.py` into a domain-local service module while preserving the existing `NotificationBot` method compatibility.

This advances `docs/架构审计.md` P2 item 5 by reducing mixed responsibilities in the large notification bot domain file through a behavior-preserving slice.

## Requirements

* Extract the implementation of these `NotificationBot` behaviors into `app/domains/notifications/notification_bot_search_command_service.py`:
  * `_cmd_search`
  * `_extract_tech_info`
* Keep original `NotificationBot._cmd_search(chat_id, text, platform)` as a compatibility wrapper with the same signature.
* Keep original `NotificationBot._extract_tech_info(item)` as a compatibility wrapper with the same signature.
* Preserve current admin user lookup, Emby search/detail/sample request paths/params/timeouts, media technical info formatting, overview HTML stripping/truncation, base URL normalization, play-link keyboard, image fallback order, `send_photo` usage, and user-facing messages.
* Preserve legacy dependency/monkeypatch behavior for `bot_service.media_api`, `bot_service.get_admin_id`, `bot_service.get_media_server_main_public_or_host`, `bot_service.get_media_server_host`, `bot_service.REPORT_COVER_URL`, `bot.send_message`, `bot.send_photo`, and `bot._download_emby_image`.

## Acceptance Criteria

* [ ] New service module owns the `/search` command implementation and tech-info formatter implementation.
* [ ] `bot_service.py` imports and configures the service through lazy providers.
* [ ] Existing callers continue through old `NotificationBot._cmd_search` and `_extract_tech_info`.
* [ ] Focused tests cover missing search keyword, missing admin ID, non-200 search response, empty search results, movie result formatting with play keyboard and image fallback, series result formatting with episode sample tech info, no-http base URL normalization, and search exception fallback.
* [ ] Focused tests and full test suite pass through `uv run`.
* [ ] Code/test changes are committed separately from Trellis archive and journal commits.

## Definition of Done

* Tests added or updated for the extracted boundary.
* `uv run pytest tests/ -v` passes.
* `git diff --check` passes.
* Task is archived and session journal records the work commit.

## Technical Approach

Create `notification_bot_search_command_service.py` with `set_dependency_providers(...)` and functions that accept the `NotificationBot` instance when legacy instance helpers are needed:

* `extract_tech_info(item)`
* `cmd_search(bot, chat_id, text, platform)`

Providers should be lazy so tests and runtime monkeypatches against `bot_service` globals still work:

* `media_api_provider=lambda: media_api`
* `admin_id_provider=lambda: get_admin_id`
* `media_server_main_public_or_host_provider=lambda: get_media_server_main_public_or_host`
* `media_server_host_provider=lambda: get_media_server_host`
* `report_cover_url_provider=lambda: REPORT_COVER_URL`

## Out of Scope

* Changing `/search` command syntax.
* Changing result limits, request fields, messages, keyboard layout, image fallback behavior, or error behavior.
* Moving `_cmd_stats` or report generation in this slice.

## Technical Notes

* Audit target: `docs/架构审计.md` P2 item 5.
* Current command implementation lives in `NotificationBot._cmd_search`.
* Current technical-info helper lives in `NotificationBot._extract_tech_info`.
* This task follows the same compatibility-preserving provider pattern as recent notification bot command service extractions.
