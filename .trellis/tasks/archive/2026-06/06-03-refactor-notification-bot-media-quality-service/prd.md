# Refactor Notification Bot Media Quality Service

## Goal

Split media-admin lookup and media quality parsing out of `app/domains/notifications/bot_service.py` into a domain-local named service module, reducing mixed responsibilities in the large notification bot file while preserving notification formatting behavior.

## Requirements

* Extract `get_admin_id()` and `get_media_quality_info(item_id)` implementation into a new `app/domains/notifications/*_service.py` module.
* Keep `bot_service.get_admin_id()` and `bot_service.get_media_quality_info(item_id)` as compatibility wrappers used by existing notification and command code.
* Preserve admin user selection fallback, media item fetch paths, filename-first quality parsing, MediaStreams fallback, PlaybackInfo fallback, HDR detection order, codec/audio formatting, empty-result behavior, and existing log messages.
* Configure dependencies from `bot_service.py` through lazy providers so legacy globals and tests can still monkeypatch `media_api` and `logger`.
* Do not change library notification templates, notification send flow, or Emby API contracts.

## Acceptance Criteria

* [ ] `bot_service.py` delegates media quality helpers to the extracted service.
* [ ] New focused boundary coverage verifies representative filename parsing, stream fallback/HDR detection, missing admin/item handling, and legacy monkeypatch compatibility.
* [ ] Existing media quality regression remains green.
* [ ] Changed modules compile and import through `uv run`.
* [ ] Full `uv run pytest tests/ -v` passes before the work commit.

## Definition of Done

* Run focused compile/import checks for changed files.
* Run focused media quality tests.
* Run the full test suite.
* Commit code/test changes separately from Trellis archive and journal bookkeeping.
* Archive the Trellis task and record a session journal entry referencing the work commit.

## Technical Approach

Create `notification_bot_media_quality_service.py` with `set_dependency_providers(...)`, `get_admin_id()`, and `get_media_quality_info(item_id)`. `bot_service.py` will configure lazy providers for `media_api` and `logger`, then retain wrapper functions with the existing names.

## Decision (ADR-lite)

Context: `bot_service.py` still mixes lifecycle, notification formatting, Telegram/WeCom transport, callbacks, admin commands, and media quality parsing.

Decision: Extract only the media quality parsing helpers in this slice because they are cohesive, module-level, and have a narrow Emby API/logging dependency surface.

Consequences: The notification bot file shrinks while existing notification rendering and tests keep calling the same public functions. Later notification formatting slices can depend directly on the media quality service once compatibility wrappers are no longer needed.

## Out of Scope

* Changing notification templates or message text.
* Moving library notification event handlers.
* Changing Emby API client behavior.
* Refactoring admin bot command handlers.

## Technical Notes

* Architecture audit target: `docs/架构审计.md` P2 item 5, large mixed-responsibility domain files.
* Applicable specs: `.trellis/spec/backend/index.md`, `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/backend/logging-guidelines.md`, `.trellis/spec/guides/index.md`.
* Primary file inspected: `app/domains/notifications/bot_service.py`.
* Existing regression: `tests/test_bootstrap_stop_hooks.py::test_notification_media_quality_uses_color_transfer_hdr_fallback`.
