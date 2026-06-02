# Notification Daemon Lifecycle Convergence

## Context

`docs/架构审计.md` lists incomplete lifecycle management as a P1 architecture risk. `app/domains/notifications/bot_service.py` is a bootstrap-started notification service and still has `SystemDaemon` background threads that only observe `running = False`; the scheduler and library notification loops use `time.sleep(...)`, and `stop()` does not join or clear thread handles.

## Scope

- Add a stop event to `SystemDaemon`.
- Make `SystemDaemon.start()` clear the stop event and keep duplicate starts idempotent.
- Make `SystemDaemon.stop()` set the stop event, unsubscribe events, join the scheduler/library threads briefly, and clear stopped thread handles.
- Replace long waits in `_scheduler_loop()` and `_library_notify_loop()` with stop-event waits.
- Preserve notification behavior, event names, queue semantics, and response payloads.
- Add focused regression tests for stop/restart behavior and event subscription reversibility.

## Out Of Scope

- Wrapper/pass-through function cleanup handled on other branches.
- NotificationBot polling lifecycle changes.
- User bot service scheduler cleanup.
- Route response or notification message formatting changes.

## Verification

- Compile changed files with `uv run python -m compileall`.
- Run focused notification lifecycle tests.
- Run full `uv run pytest tests/ -v` before committing.
