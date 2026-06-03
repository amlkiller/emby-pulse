# Refactor Notification Bot Playback Event Service

## Goal

Continue the architecture-audit refactor by extracting `NotificationBot.on_playback_event()` from the large `bot_service.py` file into a focused notification-domain service module. Preserve playback notification enablement, mute handling, media detail enrichment, progress formatting, template rendering fallback, playback URL generation, image fallback order, sending behavior, and the legacy `NotificationBot.on_playback_event()` entry point.

## Requirements

* Add a notification-domain module responsible for notification bot playback event handling.
* Move `on_playback_event(data, action)` implementation into the new module.
* Keep `NotificationBot.on_playback_event()` as a compatibility wrapper.
* Preserve `get_enable_notify()` gating and info log when disabled.
* Preserve payload extraction from `Session`, `Item`, `NowPlayingItem`, and `User`.
* Preserve received-event info logging with action, user name, and user id.
* Preserve playback mute check through `bot._is_muted(user_id, "playback")` and mute info log.
* Preserve position/runtime tick extraction, integer coercion fallback, and `bot._format_ticks()` based progress formatting.
* Preserve media detail enrichment through `media_api.get()` for item details, session playback position, and episode series details.
* Preserve swallowed detail lookup failures.
* Preserve overview HTML stripping, empty fallback, truncation, rating fallback, title/type formatting, episode `ep_info`, and audio artist formatting.
* Preserve location lookup through `get_location(ip)` and client/device defaults.
* Preserve template key selection: `playback_start` for start, `playback_stop` otherwise.
* Preserve custom `notify_template` plugin lookup and render behavior, including default-template fallback.
* Preserve default message text and timestamp format.
* Preserve jump target selection for episodes and audio albums.
* Preserve base URL fallback from `get_media_server_main_public_or_host()` to `get_media_server_host()` and automatic `https://` prefix for host-like values.
* Preserve playback keyboard generation only when the base URL is HTTP(S).
* Preserve image fallback order: target backdrop/primary, item backdrop/primary fallback when target images are missing, then `REPORT_COVER_URL`, for Telegram and WeCom.
* Preserve `send_photo("sys_notify", ..., platform="all", wecom_photo_io=wecom_img)`.
* Preserve outer error logging: `[Bot] Playback event error: ...`.
* Use lazy providers for all legacy globals and dynamic plugin lookup so monkeypatches on `bot_service` remain effective.

## Acceptance Criteria

* [ ] `bot_service.py` line count is reduced by moving playback event handling into a new domain-local module.
* [ ] `NotificationBot.on_playback_event()` delegates to the new service.
* [ ] Disabled playback notifications skip all side effects after the disabled log.
* [ ] Muted users skip send after the mute log.
* [ ] Detail enrichment, session position fallback, episode series fallback, and progress formatting preserve behavior.
* [ ] Default and plugin-rendered playback captions preserve existing behavior.
* [ ] Episode/audio jump target and image fallback behavior are preserved.
* [ ] Outer failures are logged and swallowed.
* [ ] Focused playback-event tests pass.
* [ ] Full test suite passes before code commit.

## Definition of Done

* Tests added or updated for the extracted playback-event boundary.
* Focused compile/import verification passes.
* Focused tests and full tests pass through `uv run`.
* Work commit is separate from Trellis archive and journal commits.

## Technical Approach

Create `app/domains/notifications/notification_bot_playback_event_service.py` with `handle_playback_event(bot, data, action)`. Configure providers from `bot_service.py` for enablement, media API, location lookup, URL settings, template plugin lookup, report cover URL, datetime, regex module, and logger. Keep `NotificationBot.on_playback_event()` as a thin wrapper.

## Decision (ADR-lite)

**Context**: `bot_service.py` still contains playback notification assembly, media enrichment, plugin template rendering, image selection, and delivery mixed into the bot class.

**Decision**: Extract only playback event notifications in this slice. Leave playback command handling, library episode grouping, and request callbacks for later slices.

**Consequences**: Playback event behavior becomes independently testable and `bot_service.py` shrinks without changing event subscription names or delivery APIs.

## Out of Scope

* Changing notification copy, icons, HTML, or timestamp format.
* Changing notify-template plugin behavior.
* Changing playback command behavior.
* Changing event subscription names or bus handling.
* Changing media API enrichment behavior.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Current target: `app/domains/notifications/bot_service.py`.
* Existing extraction pattern: notification bot named service modules with lazy dependency providers and legacy wrappers.
