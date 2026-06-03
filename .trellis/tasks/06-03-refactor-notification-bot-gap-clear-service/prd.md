# Refactor Notification Bot Gap Clear Service

## Goal

Continue the architecture-audit refactor by extracting `SystemDaemon._clear_gap_record_async()` from the large `bot_service.py` file into a focused notification-domain service module. Preserve episode gap cleanup behavior and keep the legacy `SystemDaemon._clear_gap_record_async()` entry point.

## Requirements

* Add a notification-domain module responsible for clearing gap records after episode webhook events.
* Move `_clear_gap_record_async()` implementation into the new module.
* Keep `SystemDaemon._clear_gap_record_async()` as a compatibility wrapper.
* Preserve early return when `item.get("Type") != "Episode"`.
* Preserve extraction and conversion:
  * `series_id = str(item.get("SeriesId"))`
  * `season = int(item.get("ParentIndexNumber", -1))`
  * `episode = int(item.get("IndexNumber", -1))`
* Preserve early return when `season == -1 or episode == -1`.
* Preserve `gap_dao.delete_gap_record_by_series_episode(series_id, season, episode)`.
* Preserve best-effort `remove_gap_from_scan_state(series_id, season, episode)` after DAO deletion.
* Preserve swallowed exceptions for scan-state removal.
* Preserve swallowed outer exceptions.
* Use lazy providers for legacy globals so monkeypatches on `bot_service` remain effective.

## Acceptance Criteria

* [ ] `bot_service.py` line count is reduced by moving gap clear handling into a new domain-local module.
* [ ] `SystemDaemon._clear_gap_record_async()` delegates to the new service.
* [ ] Non-episode items skip all side effects.
* [ ] Missing or invalid season/episode values skip side effects via the existing swallowed-error behavior.
* [ ] Valid episode items delete the gap record with existing arguments.
* [ ] Valid episode items remove the scan-state gap after DAO deletion.
* [ ] Scan-state removal failures are swallowed after DAO deletion.
* [ ] Outer failures are swallowed.
* [ ] Focused gap clear tests pass.
* [ ] Full test suite passes before code commit.

## Definition of Done

* Tests added for the extracted gap-clear boundary.
* Focused compile/import verification passes.
* Focused tests and full tests pass through `uv run`.
* Work commit is separate from Trellis archive and journal commits.

## Technical Approach

Create `app/domains/notifications/notification_bot_gap_clear_service.py` with `clear_gap_record(item)`. Configure providers from `bot_service.py` for `gap_dao` and `remove_gap_from_scan_state`. Keep `SystemDaemon._clear_gap_record_async()` as a thin wrapper.

## Decision (ADR-lite)

**Context**: `bot_service.py` still contains media-request gap cleanup detail inside the notification daemon class.

**Decision**: Extract only gap record cleanup in this slice. Leave library queueing, episode grouping, and notification publishing for later slices.

**Consequences**: Gap cleanup behavior becomes independently testable and `bot_service.py` shrinks without changing media request DAO or scan-state contracts.

## Out of Scope

* Changing gap DAO contracts.
* Changing scan-state removal behavior.
* Changing webhook event routing or library queue behavior.
* Adding new logging.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Current target: `app/domains/notifications/bot_service.py`.
* Existing extraction pattern: notification bot named service modules with lazy dependency providers and legacy wrappers.
