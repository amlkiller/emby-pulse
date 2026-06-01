# Plugin Scheduler Stop Events Batch 3

## Goal

Continue the P1 lifecycle work from `docs/架构审计.md` by making the remaining small group of long-running plugin check/schedule loops interruptible and restart-safe.

## Requirements

- Add stop-event based lifecycle control for plugins that use `_running + saved thread + sleep loop`:
  - `user_backup`
  - `hdhive`
  - `hdhivesign`
- Preserve plugin enable/disable behavior and user-facing logs.
- Keep scheduler/check intervals and business logic unchanged.
- Make `on_enable()` idempotent while the saved loop thread is alive.
- Make `on_disable()` signal the loop, join briefly, clear stopped thread handles, and allow later re-enable.
- Replace long scheduler/check loop `time.sleep(...)` waits with interruptible `Event.wait(...)`.
- Add focused regression tests for stop/restart behavior.

## Acceptance Criteria

- [x] The three target plugins each have a stop event and saved thread handle lifecycle.
- [x] The three target plugins skip duplicate loop starts while a thread is alive.
- [x] The three target plugins clear stopped thread handles on disable.
- [x] Long loop waits are interruptible by plugin disable.
- [x] Focused plugin lifecycle tests pass.
- [x] Compile verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

- Add `self._stop_event = threading.Event()` in each plugin constructor.
- Keep plugin-local lifecycle logic in `on_enable()` / `on_disable()` to match current style.
- Use `self._stop_event.clear()` before starting and `self._stop_event.set()` before joining.
- Replace scheduler/check loop sleeps with `self._stop_event.wait(...)`.
- Keep joins short (`timeout=1`) to avoid blocking plugin disable.

## Out of Scope

- Do not change checkin, backup, search, transfer, route payload, config, or notification behavior.
- Do not refactor one-off worker threads used for search, link processing, unlock/transfer, report sending, or similar user-triggered actions.
- Do not change retry sleeps outside the long-running loop body.

## Verification Plan

- Compile: `uv run --with-requirements requirements.txt python -m compileall app/plugins/user_backup/plugin.py app/plugins/hdhive/plugin.py app/plugins/hdhivesign/plugin.py tests/test_plugin_scheduler_stop_events.py`.
- Focused tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/test_plugin_scheduler_stop_events.py -v`.
- Full tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v`.

## Verification Results

- `uv run --with-requirements requirements.txt --with pytest pytest tests/test_plugin_scheduler_stop_events.py -v`: 18 passed, 1 warning.
- `uv run --with-requirements requirements.txt python -m compileall app/plugins/user_backup/plugin.py app/plugins/hdhive/plugin.py app/plugins/hdhivesign/plugin.py tests/test_plugin_scheduler_stop_events.py`: passed.
- `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v`: 105 passed, 3 warnings.
- Search assertion: no remaining long-loop `time.sleep(30|60|300|3600)`, old unnamed saved loop thread construction, or `join(timeout=5)` patterns in `user_backup`, `hdhive`, or `hdhivesign`.
