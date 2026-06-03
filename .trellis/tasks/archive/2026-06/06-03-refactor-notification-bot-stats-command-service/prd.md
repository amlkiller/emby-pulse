# Refactor Notification Bot Stats Command Service

## Goal

Split the notification bot stats/report command implementation out of `app/domains/notifications/bot_service.py` into a domain-local service module while preserving the existing `NotificationBot` method compatibility.

This advances `docs/架构审计.md` P2 item 5 by reducing mixed responsibilities in the large notification bot domain file through a behavior-preserving slice.

## Requirements

* Extract the implementation of `NotificationBot._cmd_stats` into `app/domains/notifications/notification_bot_stats_command_service.py`.
* Keep original `NotificationBot._cmd_stats(chat_id, period='day', platform='tg')` as a compatibility wrapper with the same signature.
* Preserve current period handling for day/yesterday/week/month/year, playback SQL queries, view_report plugin config reads, exclude type handling, top user lookup through `bot._get_username`, TV/movie grouping and ranking, poster mode when `HAS_PIL` and poster generation succeeds, fallback text/photo behavior, logging, traceback printing, and failure message.
* Preserve legacy dependency/monkeypatch behavior for `bot_service.get_base_filter`, `bot_service.playback_store`, `bot_service.report_gen`, `bot_service.HAS_PIL`, `bot_service.REPORT_COVER_URL`, `bot_service.logger`, dynamic `app.plugins.get_plugin_config`, and `bot.send_photo` / `bot.send_message`.

## Acceptance Criteria

* [ ] New service module owns the stats command implementation.
* [ ] `bot_service.py` imports and configures the service through lazy providers.
* [ ] Existing callers continue through old `NotificationBot._cmd_stats`.
* [ ] Focused tests cover fallback text report, poster mode report, plugin exclude type config parsing, missing data fallback labels, and DB/error failure behavior.
* [ ] Focused tests and full test suite pass through `uv run`.
* [ ] Code/test changes are committed separately from Trellis archive and journal commits.

## Definition of Done

* Tests added or updated for the extracted boundary.
* `uv run pytest tests/ -v` passes.
* `git diff --check` passes.
* Task is archived and session journal records the work commit.

## Technical Approach

Create `notification_bot_stats_command_service.py` with `set_dependency_providers(...)` and:

* `cmd_stats(bot, chat_id, period='day', platform='tg')`

Providers should be lazy so tests and runtime monkeypatches against `bot_service` globals still work:

* `base_filter_provider=lambda: get_base_filter`
* `playback_store_provider=lambda: playback_store`
* `report_gen_provider=lambda: report_gen`
* `has_pil_provider=lambda: HAS_PIL`
* `report_cover_url_provider=lambda: REPORT_COVER_URL`
* `logger_provider=lambda: logger`

The dynamic `app.plugins.get_plugin_config` lookup should remain lazy inside the service to preserve legacy plugin monkeypatch behavior.

## Out of Scope

* Changing stats command syntax or period aliases.
* Changing SQL strings, response text, ranking logic, poster generation, or plugin config semantics.
* Moving report generation, playback store queries, or plugin configuration ownership in this slice.

## Technical Notes

* Audit target: `docs/架构审计.md` P2 item 5.
* Current command implementation lives in `NotificationBot._cmd_stats`.
* `EmbyPulseOrchestrator.push_now` also reaches this command through the old wrapper.
* This task follows the same compatibility-preserving provider pattern as recent notification bot command service extractions.
