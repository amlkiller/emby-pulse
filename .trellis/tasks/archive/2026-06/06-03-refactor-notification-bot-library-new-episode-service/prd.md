# Refactor Notification Bot Library New Episode Service

## Goal

Continue the architecture-audit refactor by extracting `NotificationBot.on_library_new_episode()` from the large `bot_service.py` file into a focused notification-domain service module. Preserve episode grouping text, media quality lookup, template rendering fallback, playback URL generation, image fallback order, channel selection, Telegram channel fan-out, and the legacy `NotificationBot.on_library_new_episode()` entry point.

## Requirements

* Add a notification-domain module responsible for grouped library-new-episode handling.
* Move `on_library_new_episode(data)` implementation into the new module.
* Keep `NotificationBot.on_library_new_episode()` as a compatibility wrapper.
* Preserve `get_enable_library_notify()` gating.
* Preserve payload expectations for `series_id`, `episodes`, and `series_info`.
* Preserve season grouping by `ParentIndexNumber`, episode index de-duplication, range formatting, total episode count, and single-episode title suffix behavior.
* Preserve series field defaults for name, year, rating, overview, and server id.
* Preserve overview HTML stripping, empty overview fallback, and overview truncation.
* Preserve media quality lookup through the first episode id and existing info logs before/after lookup.
* Preserve base URL fallback from `get_media_server_main_public_or_host()` to `get_media_server_host()` and automatic `https://` prefix for host-like values.
* Preserve custom `notify_template` plugin rendering for `library_new_episode`, including default-template fallback.
* Preserve playback keyboard generation only when the base URL is HTTP(S).
* Preserve image fallback order: backdrop, primary, then `REPORT_COVER_URL`, for Telegram and WeCom.
* Preserve `get_notify_channels("library_new")` channel selection and platform mapping.
* Preserve `send_photo("sys_notify", ..., platform=platform, wecom_photo_io=wecom_img)` when platform is not `none`.
* Preserve Telegram channel fan-out with `_notify_channels(tg_img, caption, keyboard, "episode", series_info)` when `tg_channel` is enabled.
* Use lazy providers for all legacy globals and dynamic plugin lookup so monkeypatches on `bot_service` remain effective.

## Acceptance Criteria

* [ ] `bot_service.py` line count is reduced by moving grouped episode notification handling into a new domain-local module.
* [ ] `NotificationBot.on_library_new_episode()` delegates to the new service.
* [ ] Disabled library notifications skip all side effects.
* [ ] Episode grouping/range text preserves existing behavior.
* [ ] Default and plugin-rendered captions preserve existing behavior.
* [ ] Platform selection for `tg_bot`, `wecom`, both, or neither is preserved.
* [ ] Telegram channel fan-out behavior is preserved.
* [ ] Image fallback and playback keyboard generation are preserved.
* [ ] Focused library-new-episode tests pass.
* [ ] Full test suite passes before code commit.

## Definition of Done

* Tests added or updated for the extracted library-new-episode boundary.
* Focused compile/import verification passes.
* Focused tests and full tests pass through `uv run`.
* Work commit is separate from Trellis archive and journal commits.

## Technical Approach

Create `app/domains/notifications/notification_bot_library_new_episode_service.py` with `handle_library_new_episode(bot, data)`. Configure providers from `bot_service.py` for enablement, media quality lookup, URL settings, template plugin lookup, notification channels, report cover URL, datetime, regex module, and logger. Keep `NotificationBot.on_library_new_episode()` as a thin wrapper.

## Decision (ADR-lite)

**Context**: `bot_service.py` still contains grouped episode notification formatting, plugin template rendering, image selection, delivery, and channel fan-out mixed into the bot class.

**Decision**: Extract only grouped library episode notifications in this slice. Leave library polling/group detection and gap-cleared notifications for later slices.

**Consequences**: Grouped episode notification behavior becomes independently testable and `bot_service.py` shrinks without changing event subscription names, payload shape, or delivery APIs.

## Out of Scope

* Changing notification copy, icons, HTML, or timestamp format.
* Changing notify-template plugin behavior.
* Changing library polling or fresh episode grouping logic.
* Changing library-new-item handling.
* Changing channel notification behavior.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Current target: `app/domains/notifications/bot_service.py`.
* Existing extraction pattern: notification bot named service modules with lazy dependency providers and legacy wrappers.
