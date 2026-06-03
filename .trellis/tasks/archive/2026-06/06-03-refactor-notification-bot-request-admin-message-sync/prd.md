# Refactor Notification Bot Request Admin Message Sync

## Goal

Split the request-admin Telegram message-copy synchronization helpers out of `app/domains/notifications/bot_service.py` into a domain-local named service module, reducing mixed responsibilities in the large notification bot file while preserving request approval callback behavior.

## Requirements

* Extract `_ensure_request_admin_messages_table()`, `_extract_request_tmdb_id()`, `_record_request_admin_message()`, and `_sync_request_admin_messages()` implementation into a new `app/domains/notifications/*_service.py` module.
* Keep the same helper names in `bot_service.py` as compatibility wrappers used by existing send/callback code.
* Preserve DAO calls, Telegram edit method selection, fallback text behavior, duplicate row suppression, cleanup behavior, and existing logging messages.
* Configure dependencies from `bot_service.py` through lazy providers so legacy globals and tests can still monkeypatch DAO, Telegram client, and logger names.
* Do not change request approval/reject/manual callback behavior, MoviePilot interaction, or notification send behavior.

## Acceptance Criteria

* [ ] `bot_service.py` delegates request-admin message sync helpers to the extracted service.
* [ ] New focused boundary coverage verifies representative extract, record, sync, duplicate suppression, and fallback/no-row branches through legacy monkeypatches.
* [ ] Changed modules compile and import through `uv run`.
* [ ] Full `uv run pytest tests/ -v` passes before the work commit.

## Definition of Done

* Run focused compile/import checks for changed files.
* Run focused request-admin message sync tests.
* Run the full test suite.
* Commit code/test changes separately from Trellis archive and journal bookkeeping.
* Archive the Trellis task and record a session journal entry referencing the work commit.

## Technical Approach

Create `notification_bot_request_admin_message_sync_service.py` with `set_dependency_providers(...)` and the four helper implementations. `bot_service.py` will configure lazy providers for `bot_service_dao`, `telegram_client`, and `logger`, then retain helper wrappers that delegate to the new service.

## Decision (ADR-lite)

Context: `bot_service.py` still owns lifecycle, event handling, notification formatting, Telegram/WeCom sends, callbacks, and admin commands in one large module.

Decision: Extract only the request-admin message-copy synchronization helpers in this slice because the helper group is cohesive, module-level, and already has a narrow DAO/Telegram dependency surface.

Consequences: The notification bot file shrinks without changing callback behavior. Later callback-dispatch or send-channel slices can reuse this extracted service directly once compatibility wrappers are no longer needed.

## Out of Scope

* Moving `NotificationBot._handle_callback()`.
* Changing request approval/reject/manual status transitions.
* Changing Telegram send/photo behavior.
* Refactoring bot admin router endpoints.

## Technical Notes

* Architecture audit target: `docs/架构审计.md` P2 item 5, large mixed-responsibility domain files.
* Applicable specs: `.trellis/spec/backend/index.md`, `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/backend/logging-guidelines.md`, `.trellis/spec/guides/index.md`.
* Primary file inspected: `app/domains/notifications/bot_service.py`.
