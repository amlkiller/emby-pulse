# System task poller cancellation lifecycle convergence

## Goal

Make the bootstrap-started Emby scheduled-task poller match the project's lifecycle conventions by giving its async loop an explicit cancellable condition and preserving restart-safe stop behavior.

## What I already know

* `app/domains/system/tasks.py` is registered through bootstrap service lifecycle tests.
* `start_task_poller()` saves the created asyncio task and guards duplicate starts.
* `stop_task_poller()` cancels the saved task and clears task/started flags.
* `poll_emby_tasks()` still uses `while True` plus `asyncio.sleep(5)`, which is less explicit than the lifecycle contract for cancellable long-running loops.
* Existing tests already cover cancellation and restart for this service in `tests/test_bootstrap_stop_hooks.py`.

## Requirements

* Replace the unconditional async poller loop with a cancellation-aware loop condition that uses the saved task state.
* Keep the public start/stop API and response behavior unchanged.
* Preserve idempotent start behavior and restart after stop.
* Add or update focused tests that assert the poller no longer uses `while True` and still awaits an interruptible async sleep interval.

## Acceptance Criteria

* [ ] `poll_emby_tasks()` does not contain `while True`.
* [ ] `poll_emby_tasks()` still awaits `asyncio.sleep(5)` between polls.
* [ ] `stop_system_task_services()` cancels the task, clears state, and allows restart.
* [ ] Changed Python files compile through `uv run`.
* [ ] Focused lifecycle tests pass.
* [ ] Full test suite passes with `uv run pytest tests/ -v`.

## Definition of Done

* Tests added or updated for the lifecycle contract.
* Compile check, focused tests, and full test suite pass under the locked uv environment.
* Spec update considered; update only if new durable convention is learned.
* Work changes committed before Trellis archive and journal commits.

## Technical Approach

Use the existing module-level `_task_poller_started` flag as the loop predicate. `start_task_poller()` sets it before the loop runs; `stop_task_poller()` clears it and cancels the saved task. Let `asyncio.CancelledError` propagate so cancellation remains visible to the event loop and the existing cancellation test continues to assert a cancelled task.

## Decision (ADR-lite)

Context: The system task poller is a bootstrap-started lifecycle service and should not rely on an unconditional infinite loop.

Decision: Keep the existing asyncio task model, but make the loop condition explicit with `_task_poller_started`.

Consequences: Shutdown remains cancellation-based and restart-safe while static inspection can distinguish this loop from uncontrolled `while True` background work.

## Out of Scope

* Refactoring task notification message content.
* Changing Emby polling interval or external API behavior.
* Wrapper/pass-through cleanup.
* Refactoring transient user-initiated polling sleeps in media request download helpers.

## Technical Notes

* Relevant specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/guides/index.md`.
* Relevant files: `app/domains/system/tasks.py`, `tests/test_bootstrap_stop_hooks.py`.
