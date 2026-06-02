# User Bot Polling Lifecycle Convergence

## Goal

Make the notification `UserBot` Telegram polling and scheduler threads stoppable, joinable, and restartable in the same process, following the lifecycle contract called out by `docs/架构审计.md` and `.trellis/spec/backend/directory-structure.md`.

## Requirements

- Add an instance-level stop event to `UserBot`.
- Make `UserBot.start()` clear the stop event before starting background threads.
- Name the polling and scheduler threads for diagnostics and lifecycle tests.
- Make `UserBot.stop()` set the stop event, flush pending batch usage, join both worker threads briefly, and clear stopped thread handles.
- Replace fixed retry and scheduler sleeps in the long-running loops with stop-event waits where shutdown should be interruptible.
- Preserve existing Telegram polling, command setup, task dispatch, scheduler work, and batch flush behavior.
- Add focused regression tests for user bot thread stop/restart behavior.

## Acceptance Criteria

- [ ] Repeated `UserBot.start()` calls still avoid duplicate thread starts while running.
- [ ] `UserBot.stop()` joins both polling and scheduler threads with a short timeout.
- [ ] `UserBot.stop()` clears stopped thread handles so a later `start()` creates fresh threads.
- [ ] Polling retry waits and scheduler initial/interval waits can be interrupted by the stop event.
- [ ] Focused lifecycle tests pass.
- [ ] Full `uv run pytest tests/ -v` passes before committing.

## Definition of Done

- Code changes are behavior-preserving outside lifecycle shutdown/restart control.
- Verification uses `uv run` project commands.
- New durable conventions are added to `.trellis/spec/` only if this task discovers something not already covered.
- A work commit is created before Trellis archive and journal commits.

## Technical Approach

Follow the established lifecycle pattern already used by notification daemon and notification bot polling: store `threading.Event` on the service instance, name worker threads, use `Event.wait(...)` for interruptible waits, join briefly on stop, clear stopped handles, and allow restart in tests or reloads.

## Out of Scope

- Wrapper/pass-through cleanup handled on other branches.
- Notification route response changes.
- User bot message/callback formatting changes.
- Batch flush thread lifecycle beyond preserving current stop signal and forced flush behavior.

## Technical Notes

- Target file: `app/domains/notifications/user_bot_service.py`.
- Existing stop path is called from `app/domains/notifications/bot_service.py::stop_notification_services()`.
- Applicable specs: backend directory structure lifecycle contract, backend quality guidelines, backend logging guidelines.
