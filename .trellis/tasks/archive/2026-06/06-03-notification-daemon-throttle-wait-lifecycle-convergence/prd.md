# Notification Daemon Throttle Wait Lifecycle Convergence

## Goal

Make remaining fixed throttle sleeps inside the bootstrap-started notification daemon interruptible by `stop_notification_services()`.

## Requirements

* Replace `SystemDaemon._process_library_group()` fixed `time.sleep(2)` throttle with `self._stop_event.wait(2)`.
* Replace `SystemDaemon._sync_pending_requests()` fixed `time.sleep(0.5)` throttle with `self._stop_event.wait(0.5)`.
* Preserve normal throttling behavior while the daemon is running.
* Return early from the current work loop when the stop event is set during a throttle wait.
* Add focused source-level lifecycle assertions for the daemon work methods.

## Acceptance Criteria

* [ ] `SystemDaemon._process_library_group()` uses `_stop_event.wait(2)` and contains no `time.sleep`.
* [ ] `SystemDaemon._sync_pending_requests()` uses `_stop_event.wait(0.5)` and contains no `time.sleep`.
* [ ] Existing notification service start/stop tests still pass.
* [ ] Compile checks, focused pytest, and full pytest pass through `uv run`.

## Definition of Done

* Behavior-preserving lifecycle slice is implemented.
* Regression tests protect the interruptible waits.
* Trellis specs reviewed; update only if this introduces new durable guidance beyond the existing lifecycle rule.
* Work commit lands before task archive and journal commits.

## Technical Approach

Use the existing `SystemDaemon._stop_event` as the authority for the two throttle waits. When `wait(...)` returns `True`, return from the current method so shutdown is not delayed by queued library or pending-request work. Extend `tests/test_bootstrap_stop_hooks.py` to inspect the affected methods.

## Out of Scope

* NotificationBot polling lifecycle, already covered by existing stop-event tests.
* User bot transient helper sleeps.
* Plugin worker thread ownership.
* Wrapper/pass-through cleanup.

## Technical Notes

* Audit source: `docs/架构审计.md` P1 lifecycle management.
* Relevant spec: `.trellis/spec/backend/directory-structure.md` stop-event guidance for lifecycle loops.
* Target files: `app/domains/notifications/bot_service.py`, `tests/test_bootstrap_stop_hooks.py`.
