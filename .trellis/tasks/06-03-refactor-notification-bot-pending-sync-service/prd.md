# Refactor Notification Bot Pending Sync Service

## Goal

Continue the architecture-audit refactor by extracting `SystemDaemon._sync_pending_requests()` from the large `bot_service.py` file into a focused notification-domain service module. Preserve pending request lookup, media server search, movie completion, update-request episode matching, new-request season matching, stop-event interruption, logging, and the legacy `SystemDaemon._sync_pending_requests()` entry point.

## Requirements

* Add a notification-domain module responsible for pending media-request sync handling.
* Move `_sync_pending_requests()` implementation into the new module.
* Keep `SystemDaemon._sync_pending_requests()` as a compatibility wrapper.
* Preserve `media_request_dao.list_pending_sync_requests()` lookup.
* Preserve early returns when no rows exist or `get_admin_id()` is empty.
* Preserve row field usage for `tmdb_id`, `media_type`, `season`, optional `request_type`, and optional `episodes`.
* Preserve media lookup through `media_api.get(f"/Users/{admin_id}/Items", params=..., timeout=5).json()`.
* Preserve `type_filter = "Movie"` for movies and `"Series"` for non-movies.
* Preserve movie completion through `media_request_dao.mark_sync_request_finished(tid)` and info log.
* Preserve update request handling when `request_type == "update"` and `episodes` is non-empty:
  * Parse comma-separated digit episode values with `int(e)` after `strip().isdigit()`.
  * Query local episodes with parent id, include type, recursive, and fields params.
  * Match local episodes by requested season and truthy episode number.
  * Mark finished only when requested episodes are non-empty and all requested episodes are present.
  * Preserve info log format.
* Preserve new request handling:
  * Query `/Shows/{sid}/Seasons` with `{"UserId": admin_id}`, timeout 5.
  * Mark finished when requested season exists in returned season index values.
  * Preserve info log format.
* Preserve `daemon._stop_event.wait(0.5)` between rows and immediate return when it is set.
* Preserve outer error logging: `[入库同步] 定时同步异常: ...`.
* Use lazy providers for all legacy globals so monkeypatches on `bot_service` remain effective.

## Acceptance Criteria

* [ ] `bot_service.py` line count is reduced by moving pending sync handling into a new domain-local module.
* [ ] `SystemDaemon._sync_pending_requests()` delegates to the new service.
* [ ] Empty rows and missing admin id skip side effects.
* [ ] Movie pending requests are marked complete with the existing search params and log.
* [ ] Update-series pending requests are marked complete only when all requested episodes are present in the requested season.
* [ ] New-series pending requests are marked complete only when the requested season exists.
* [ ] Stop-event wait behavior is preserved.
* [ ] Outer failures are logged and swallowed.
* [ ] Focused pending-sync tests pass.
* [ ] Full test suite passes before code commit.

## Definition of Done

* Tests added or updated for the extracted pending-sync boundary.
* Existing stop-hook lifecycle test remains meaningful after moving implementation.
* Focused compile/import verification passes.
* Focused tests and full tests pass through `uv run`.
* Work commit is separate from Trellis archive and journal commits.

## Technical Approach

Create `app/domains/notifications/notification_bot_pending_sync_service.py` with `sync_pending_requests(daemon)`. Configure providers from `bot_service.py` for media request DAO, media API, admin id lookup, and logger. Keep `SystemDaemon._sync_pending_requests()` as a thin wrapper so scheduler behavior and legacy monkeypatching still work.

## Decision (ADR-lite)

**Context**: `bot_service.py` still contains pending request synchronization business logic mixed into the daemon class.

**Decision**: Extract only pending request sync in this slice. Leave the scheduler loop, library grouping, and user-expiration checks for later slices.

**Consequences**: Pending sync behavior becomes independently testable and `bot_service.py` shrinks without changing daemon scheduling or media request DAO contracts.

## Out of Scope

* Changing media request DAO contracts.
* Changing scheduler timing or bootstrap lifecycle behavior.
* Changing request status semantics.
* Changing media server search params or log text.
* Moving user expiration logic.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Current target: `app/domains/notifications/bot_service.py`.
* Existing extraction pattern: notification bot named service modules with lazy dependency providers and legacy wrappers.
