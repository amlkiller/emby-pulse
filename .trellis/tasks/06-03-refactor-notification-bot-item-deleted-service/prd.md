# Refactor Notification Bot Item Deleted Service

## Goal

Continue the architecture-audit refactor by extracting `NotificationBot.on_item_deleted()` from the large `bot_service.py` file into a focused notification-domain service module. Preserve item-deletion notification enablement, user-deletion skip behavior, duplicate suppression, message formatting, image fallback order, TMDB poster fallback, delivery, error swallowing, logging, and the legacy `NotificationBot.on_item_deleted()` entry point.

## Requirements

* Add a notification-domain module responsible for notification bot item-deletion handling.
* Move `on_item_deleted()` implementation into the new module.
* Keep `NotificationBot.on_item_deleted()` as a compatibility wrapper.
* Preserve `get_notify_item_deleted()` gating.
* Preserve payload extraction from `data.get("Item") or data`.
* Preserve skipping user deletion notifications when `Type == "User"` or the title contains `删除了用户`.
* Preserve duplicate suppression using `bot.delete_cache`:
  * Suppress repeated `item_id` or `unique_name` notifications within 300 seconds.
  * Store both item id and unique name timestamps when available.
  * Prune entries older than 600 seconds.
* Preserve deletion type and title formatting for Movie, Series, Season, Episode, and default media cases.
* Preserve deletion message text and timestamp format.
* Preserve image fallback order:
  * Primary image.
  * Backdrop image.
  * Series primary image.
  * TMDB poster URL when no local image is available.
  * `REPORT_COVER_URL`.
* Preserve TMDB fallback behavior, including `tmdb_client.api_key`, safe proxies, movie/TV method selection, status-code check, and swallowed TMDB exceptions.
* Preserve `send_photo("sys_notify", tg_img, msg, platform="all", wecom_photo_io=tg_img)`.
* Preserve outer assembly failure logging: `删除通知组装异常: ...`.
* Use lazy providers for `get_notify_item_deleted`, `time`, `datetime`, `tmdb_client`, `get_safe_proxies`, `REPORT_COVER_URL`, and `logger` so legacy monkeypatches on `bot_service` remain effective.

## Acceptance Criteria

* [ ] `bot_service.py` line count is reduced by moving item-deletion handling into a new domain-local module.
* [ ] `NotificationBot.on_item_deleted()` delegates to the new service.
* [ ] Disabled deletion notifications skip all side effects.
* [ ] User deletion payloads are skipped.
* [ ] Duplicate suppression and cache pruning are preserved.
* [ ] Movie, series, season, episode, and default media messages preserve existing formatting.
* [ ] Local image and TMDB poster fallback order is preserved.
* [ ] TMDB fallback exceptions are swallowed.
* [ ] Outer assembly failures are logged and swallowed.
* [ ] Focused item-deletion tests pass.
* [ ] Full test suite passes before code commit.

## Definition of Done

* Tests added or updated for the extracted item-deletion boundary.
* Focused compile/import verification passes.
* Focused tests and full tests pass through `uv run`.
* Work commit is separate from Trellis archive and journal commits.

## Technical Approach

Create `app/domains/notifications/notification_bot_item_deleted_service.py` with `handle_item_deleted(bot, data)`. Configure providers from `bot_service.py` for enablement, time, datetime, TMDB client, safe proxies, report cover URL, and logger. Keep `NotificationBot.on_item_deleted()` as a thin wrapper.

## Decision (ADR-lite)

**Context**: `bot_service.py` still contains several event handlers with formatting, cache state, image lookup, external API fallback, and delivery side effects mixed into the bot class.

**Decision**: Extract only item-deletion notification handling in this slice, preserving `bot.delete_cache` ownership and existing delivery APIs.

**Consequences**: Deletion notification behavior becomes independently testable and `bot_service.py` shrinks without changing playback, library, daily report, or callback handling.

## Out of Scope

* Changing deletion notification copy, icons, HTML, or timestamp format.
* Changing duplicate suppression windows.
* Changing TMDB client behavior or transport.
* Changing event bus subscription names.
* Refactoring playback, library, or daily report handlers.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Current target: `app/domains/notifications/bot_service.py`.
* Existing extraction pattern: notification bot named service modules with lazy dependency providers and legacy wrappers.
