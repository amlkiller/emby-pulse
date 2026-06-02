# Gap Service Stop Hook

## Goal

Continue the architecture audit lifecycle refactor by making the bootstrap-started gap background refresh service stoppable and restartable in the same process.

## Requirements

- Add a `stop_gap_services()` hook next to `start_gap_services()` in `app.domains.media_requests.gaps`.
- Save the background gap sync thread handle and a stop event at module scope.
- Replace long `time.sleep(...)` waits in the bootstrap-started gap background loop with interruptible `Event.wait(...)`.
- Ensure `stop_gap_services()` resets `_gap_services_started` and clears stopped thread handles so a later `start_gap_services()` can start again.
- Route `app.bootstrap.services` registration for `"gaps"` through paired start/stop callbacks.
- Preserve gap scan API behavior, manual scan/download helpers, and gap DAO behavior.
- Add focused regression tests for stop/restart behavior and bootstrap registry stop registration.
- Update backend directory/lifecycle spec guidance if needed.

## Acceptance Criteria

- `start_gap_services()` remains idempotent.
- `stop_gap_services()` stops both the delayed-start thread and any active background sync thread without waiting for the old 5-second / 120-second / interval sleeps.
- Restarting after stop works in the same process.
- `build_bootstrap_registry(...)` registers `"gaps"` with both start and stop callbacks.
- Focused lifecycle tests, compile, ruff, `git diff --check`, and full pytest pass in one consolidated verification pass.

## Out of Scope

- Do not change gap scan result shape, route payloads, or download behavior.
- Do not change `run_scan_task()` scanning logic.
- Do not refactor other notification/media request cross-domain imports.
- Do not change plugin scheduler lifecycle in this slice.

## Technical Notes

- Audit reference: `docs/架构审计.md` P1 issue 3, lifecycle management incomplete.
- Existing pattern references: `app.domains.media_requests.router.start_community_cache_refresh_loop()` and `app.domains.playback.calendar_service.CalendarService`.
- Existing lifecycle spec: `.trellis/spec/backend/directory-structure.md`.
