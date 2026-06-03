# Refactor Notification Bot WeCom Service

## Goal

Split Enterprise WeChat (WeCom) notification sending helpers out of `app/domains/notifications/bot_service.py` into a domain-local service module while preserving existing `NotificationBot` method compatibility.

This advances `docs/架构审计.md` P2 item 5 by reducing mixed responsibilities in the large notification bot domain file through a behavior-preserving slice.

## Requirements

* Extract the implementation of these `NotificationBot` methods into a new `app/domains/notifications/notification_bot_wecom_service.py` module:
  * `_get_wecom_token`
  * `_html_to_wecom_text`
  * `_set_wecom_menu`
  * `_send_wecom_message`
  * `_send_wecom_photo`
* Keep the original `NotificationBot` methods as compatibility wrappers.
* Preserve token cache behavior stored on the `NotificationBot` instance (`wecom_token`, `wecom_token_expires`).
* Preserve legacy dependency/monkeypatch behavior for `bot_service` globals including WeCom settings, proxy helpers, media settings, `wecom_client`, `media_api`, `REPORT_COVER_URL`, and `logger`.
* Preserve current text conversion, menu payload, text truncation, image upload/fallback, news payload, logging, and exception swallowing behavior.
* Do not change Telegram sending, command handling, or public notification facade behavior in this slice.

## Acceptance Criteria

* [ ] New service module owns the WeCom notification helper implementation.
* [ ] `bot_service.py` imports and configures the new service through lazy providers.
* [ ] Existing `NotificationBot` methods continue to work through old names and signatures.
* [ ] Focused tests cover token caching, HTML-to-WeCom text conversion, message send behavior, and photo/news fallback behavior.
* [ ] Focused tests and full test suite pass through `uv run`.
* [ ] Code/test changes are committed separately from Trellis archive and journal commits.

## Definition of Done

* Tests added or updated for the extracted boundary.
* `uv run pytest tests/ -v` passes.
* `git diff --check` passes.
* Task is archived and session journal records the work commit.

## Technical Approach

Create a small service module with `set_dependency_providers(...)` and standalone functions that accept the `NotificationBot` instance when they need token cache state:

* `get_wecom_token(bot)`
* `html_to_wecom_text(html_text, inline_keyboard=None)`
* `set_wecom_menu(bot)`
* `send_wecom_message(bot, text, inline_keyboard=None, touser="@all")`
* `send_wecom_photo(bot, photo_bytes, html_text, inline_keyboard=None, touser="@all")`

The original `NotificationBot` methods delegate to these functions. Providers should be lazy and return current objects/functions from `bot_service.py`, preserving tests and plugins that monkeypatch the legacy module globals.

## Out of Scope

* Fixing or redesigning WeCom card/image behavior.
* Moving Telegram send/edit/polling logic.
* Moving notification assembly for playback, library, login, deletion, or reports.
* Changing external client behavior or adding new WeCom APIs.
* Changing plugin/public service contracts.

## Technical Notes

* Audit target: `docs/架构审计.md` P2 item 5, "domain 已迁移，但内部仍是大文件混合职责".
* Existing references:
  * `NotificationBot.start()` calls `_set_wecom_menu`.
  * `NotificationBot.send_photo()` schedules `_send_wecom_photo`.
  * `NotificationBot.send_message()` schedules `_send_wecom_message`.
  * `tests/test_bootstrap_stop_hooks.py` monkeypatches `NotificationBot._set_wecom_menu`.
* Keep this as a small behavior-preserving extraction.
