# Refactor Notification Bot Library New Item Service

## Goal

Continue the architecture-audit refactor by extracting `NotificationBot.on_library_new_item()` from the large `bot_service.py` file into a focused notification-domain service module. Preserve library notification enablement, media formatting, quality lookup, template rendering fallback, playback URL generation, image fallback order, channel selection, Telegram channel fan-out, error logging, and the legacy `NotificationBot.on_library_new_item()` entry point.

## Requirements

* Add a notification-domain module responsible for notification bot library-new-item handling.
* Move `on_library_new_item()` implementation into the new module.
* Keep `NotificationBot.on_library_new_item()` as a compatibility wrapper.
* Preserve `get_enable_library_notify()` gating.
* Preserve item field defaults for `Name`, `ProductionYear`, `CommunityRating`, `Overview`, `Type`, `Id`, and `ServerId`.
* Preserve HTML stripping, empty overview fallback, and overview truncation behavior.
* Preserve movie/series type labels and icons.
* Preserve media quality lookup through `get_media_quality_info(item_id)`.
* Preserve base URL fallback from `get_media_server_main_public_or_host()` to `get_media_server_host()` and automatic `https://` prefix for host-like values.
* Preserve custom `notify_template` plugin rendering for `library_new_item`, including default-template fallback and warning log on render failure.
* Preserve playback keyboard generation only when the base URL is HTTP(S).
* Preserve image fallback order: backdrop, primary, then `REPORT_COVER_URL`, for Telegram and WeCom.
* Preserve `get_notify_channels("library_new")` channel selection and platform mapping.
* Preserve `send_photo("sys_notify", ..., platform=platform, wecom_photo_io=wecom_img)` when platform is not `none`.
* Preserve Telegram channel fan-out with `_notify_channels(tg_img, caption, keyboard, type_raw.lower() if type_raw else "movie", item)` when `tg_channel` is enabled.
* Preserve outer error logging: `[入库通知] 处理失败: ...`.
* Use lazy providers for all legacy globals and dynamic plugin lookup so monkeypatches on `bot_service` remain effective.

## Acceptance Criteria

* [ ] `bot_service.py` line count is reduced by moving library-new-item handling into a new domain-local module.
* [ ] `NotificationBot.on_library_new_item()` delegates to the new service.
* [ ] Disabled library notifications skip all side effects.
* [ ] Default and plugin-rendered captions preserve existing behavior.
* [ ] Platform selection for `tg_bot`, `wecom`, both, or neither is preserved.
* [ ] Telegram channel fan-out behavior is preserved.
* [ ] Image fallback and playback keyboard generation are preserved.
* [ ] Outer failures are logged and swallowed.
* [ ] Focused library-new-item tests pass.
* [ ] Full test suite passes before code commit.

## Definition of Done

* Tests added or updated for the extracted library-new-item boundary.
* Focused compile/import verification passes.
* Focused tests and full tests pass through `uv run`.
* Work commit is separate from Trellis archive and journal commits.

## Technical Approach

Create `app/domains/notifications/notification_bot_library_new_item_service.py` with `handle_library_new_item(bot, item)`. Configure providers from `bot_service.py` for enablement, media quality lookup, URL settings, template plugin lookup, notification channels, report cover URL, datetime, regex module, and logger. Keep `NotificationBot.on_library_new_item()` as a thin wrapper.

## Decision (ADR-lite)

**Context**: `bot_service.py` still contains library notification formatting, plugin template rendering, image selection, delivery, and channel fan-out mixed into the bot class.

**Decision**: Extract only single item library notifications in this slice. Leave grouped episode notifications and playback event notifications for later slices.

**Consequences**: Single item library notification behavior becomes independently testable and `bot_service.py` shrinks without changing event subscription names or delivery APIs.

## Out of Scope

* Changing notification copy, icons, HTML, or timestamp format.
* Changing notify-template plugin behavior.
* Changing library-new-episode handling.
* Changing playback event handling.
* Changing channel notification behavior.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Current target: `app/domains/notifications/bot_service.py`.
* Existing extraction pattern: notification bot named service modules with lazy dependency providers and legacy wrappers.
