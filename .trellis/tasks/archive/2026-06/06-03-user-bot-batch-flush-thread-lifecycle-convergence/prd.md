# User bot batch flush thread lifecycle convergence

## Goal

Make the user bot's module-level batch-used flush daemon follow the same lifecycle shape as other bootstrap-started notification workers: saved thread handle, stop event, join on stop, clear stopped handles, and restart in the same process.

## What I already know

* `docs/架构审计.md` calls out incomplete lifecycle management for bootstrap-started services and plugin/domain scheduler loops.
* `app/domains/notifications/user_bot_service.py` already uses `_batch_flush_stop` and `_batch_flush_thread`.
* `_batch_flush_loop()` already uses `_batch_flush_stop.wait(...)`, so the wait is interruptible.
* `UserBot.stop()` sets `_batch_flush_stop` and flushes once, but it does not join or clear `_batch_flush_thread`.
* Existing lifecycle tests in `tests/test_bootstrap_stop_hooks.py` cover `UserBot` polling and scheduler threads; they currently monkeypatch out `_start_batch_flush_thread`.

## Requirements

* Add a narrow stop helper for the batch flush thread that sets `_batch_flush_stop`, joins the saved thread briefly, and clears `_batch_flush_thread` when stopped.
* Keep forced `_flush_batch_used(force=True)` behavior on `UserBot.stop()`.
* Keep `_start_batch_flush_thread()` idempotent and restart-safe.
* Preserve current public bot start/stop behavior and response behavior.
* Add focused lifecycle test coverage for the batch flush thread handle and source-level interruptible wait contract.

## Acceptance Criteria

* [ ] Starting `UserBot` starts polling, scheduler, and batch flush threads once.
* [ ] Stopping `UserBot` sets the instance stop event and the batch flush stop event.
* [ ] Stopping `UserBot` joins and clears stopped batch flush thread handles.
* [ ] Restarting `UserBot` after stop creates a new batch flush thread.
* [ ] `_batch_flush_loop()` continues to use `_batch_flush_stop.wait(...)` and does not use `time.sleep(...)`.
* [ ] Changed Python files compile through `uv run`.
* [ ] Focused lifecycle tests pass.
* [ ] Full `uv run pytest tests/ -v` passes.

## Definition of Done

* Code and tests are committed as one work commit.
* Trellis task is archived after the work commit.
* Session journal records the work commit.
* Spec update is considered and only applied if this creates new durable guidance.

## Technical Approach

Introduce a `_stop_batch_flush_thread()` helper next to `_start_batch_flush_thread()`. Have `UserBot.stop()` call the helper before the forced flush. This keeps stop sequencing simple: signal background flush loop, join if it exits promptly, clear the handle, then synchronously persist any remaining dirty count.

## Decision (ADR-lite)

Context: The batch flush daemon is not a user-facing transient worker; it is part of the user bot lifecycle and should be restart-safe during application shutdown/reload.

Decision: Treat `_batch_flush_thread` like the other saved background worker handles and centralize its stop behavior in a module helper.

Consequences: Shutdown can interrupt the loop and clean the handle without changing registration quota semantics.

## Out of Scope

* Refactoring the large `user_bot_service.py` file into smaller modules.
* Changing registration quota behavior, batch flush interval, or Telegram command behavior.
* Wrapper/pass-through cleanup.
* Refactoring short UI/message delay sleeps.

## Technical Notes

* Relevant specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`.
* Relevant files: `app/domains/notifications/user_bot_service.py`, `tests/test_bootstrap_stop_hooks.py`.
