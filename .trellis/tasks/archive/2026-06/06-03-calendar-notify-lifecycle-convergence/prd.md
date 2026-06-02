# Calendar Notify Lifecycle Convergence

## Goal

Bring `CalendarNotifyService` fully in line with the bootstrap lifecycle contract from `docs/架构审计.md` and `.trellis/spec/backend/directory-structure.md`: named worker thread, interruptible restart, stopped-handle cleanup, and restart protection when a previous worker is still alive.

## Requirements

- Name the calendar notify worker thread for diagnostics and lifecycle tests.
- Keep `start()` idempotent while the service is already running.
- Prevent `start()` from creating a duplicate worker if a previous thread handle is still alive after stop/join timeout.
- Make `stop()` set the stop event, join briefly, and clear stopped thread handles.
- Make `restart()` use the stop event instead of fixed `time.sleep(1)` so restart delay is interruptible and does not rely on a bare sleep.
- Preserve calendar notification scheduling, send behavior, API responses, config persistence, and bootstrap registration.
- Add focused lifecycle regression coverage.

## Acceptance Criteria

- [ ] Repeated `start()` calls create only one worker while running.
- [ ] Worker thread is named.
- [ ] `stop()` joins with a short timeout and clears the stopped handle.
- [ ] Restart creates a fresh worker after a clean stop.
- [ ] Restart/start does not duplicate a still-alive worker after join timeout.
- [ ] Calendar notify loop uses the stop event for wait/exit behavior.
- [ ] Focused tests and full `uv run pytest tests/ -v` pass.

## Definition of Done

- Code changes stay behavior-preserving outside lifecycle shutdown/restart control.
- Verification uses `uv run`.
- Spec updates are only made if new durable knowledge is discovered beyond the existing lifecycle contract.
- Work commit is created before Trellis archive and journal commits.

## Out of Scope

- Wrapper/pass-through cleanup.
- Calendar notification message formatting.
- Calendar notify API authorization or response-shape changes.
- Calendar data fetching or transport changes.

## Technical Notes

- Target file: `app/domains/notifications/calendar_notify.py`.
- Existing bootstrap registration already calls `start_calendar_notify_services` and `stop_calendar_notify_services`.
- The service already has `_stop_event`; this task completes the lifecycle surface around it.
