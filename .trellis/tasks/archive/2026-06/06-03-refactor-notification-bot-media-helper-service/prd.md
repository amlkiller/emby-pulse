# Refactor Notification Bot Media Helper Service

## Goal

Split `NotificationBot` media/user helper methods out of `app/domains/notifications/bot_service.py` into a domain-local service module while preserving existing method compatibility.

This advances `docs/架构审计.md` P2 item 5 by reducing mixed responsibilities in the large notification bot domain file through a behavior-preserving slice.

## Requirements

* Extract the implementation of these `NotificationBot` helpers into `app/domains/notifications/notification_bot_media_helper_service.py`:
  * `_download_user_image`
  * `_get_username`
  * `_get_subnet_key`
  * `_save_playback_history`
  * `_download_emby_image`
* Keep original `NotificationBot` methods as compatibility wrappers with the same signatures.
* Preserve `NotificationBot.user_cache` behavior for username lookup.
* Preserve legacy dependency/monkeypatch behavior for `bot_service.media_api`, `bot_service.get_isp`, `bot_service.insert_bot_playback_history_record`, and `bot_service.logger`.
* Preserve current timeout values, image params, fallback returns, and exception swallowing/logging behavior.

## Acceptance Criteria

* [ ] New service module owns the media/user helper implementation.
* [ ] `bot_service.py` imports and configures the service through lazy providers.
* [ ] Existing helper callers continue through old `NotificationBot` method names.
* [ ] Focused tests cover image download, username cache fill/fallback, IPv6 subnet key, playback history insert, and legacy monkeypatch compatibility.
* [ ] Focused tests and full test suite pass through `uv run`.
* [ ] Code/test changes are committed separately from Trellis archive and journal commits.

## Definition of Done

* Tests added or updated for the extracted boundary.
* `uv run pytest tests/ -v` passes.
* `git diff --check` passes.
* Task is archived and session journal records the work commit.

## Technical Approach

Create `notification_bot_media_helper_service.py` with `set_dependency_providers(...)` and functions that accept the `NotificationBot` instance when cache state is needed:

* `download_user_image(user_id)`
* `get_username(bot, user_id)`
* `get_subnet_key(ip)`
* `save_playback_history(data, user_id, user_name, item, ip, location)`
* `download_emby_image(item_id, img_type="Primary", image_tag=None)`

The old `NotificationBot` methods delegate to these functions. Providers should be lazy so tests and runtime monkeypatches against `bot_service` globals still work.

## Out of Scope

* Moving notification assembly or command handlers.
* Changing playback history schema or persistence behavior.
* Changing media API params/timeouts.
* Changing cache invalidation behavior.

## Technical Notes

* Audit target: `docs/架构审计.md` P2 item 5.
* These helpers are used by library, playback, login, deletion, risk, stats, and command paths, so wrappers must remain stable.
