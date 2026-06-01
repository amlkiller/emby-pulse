# Plugin Scheduler Stop Events Batch 2

## Goal

Continue the P1 lifecycle work from `docs/架构审计.md` by making the next small batch of plugin scheduler loops interruptible and restart-safe.

## Requirements

- Add stop-event based lifecycle control for plugins that use `scheduler_thread + scheduler_running + sleep loop`:
  - `view_report`
  - `emby_restart`
- Preserve plugin enable/disable behavior and user-facing logs.
- Keep scheduler intervals and business logic unchanged.
- Make scheduler start idempotent while the scheduler thread is alive.
- Make scheduler stop signal the scheduler, join briefly, clear thread handles, and allow later re-enable.
- Replace scheduler-loop `time.sleep(...)` waits with interruptible `Event.wait(...)`.
- Add focused regression tests for stop/restart behavior.

## Acceptance Criteria

- [x] The two target plugins each have a stop event and saved thread handle lifecycle.
- [x] The two target plugins skip duplicate scheduler starts while a thread is alive.
- [x] The two target plugins clear scheduler thread handles on disable.
- [x] Scheduler-loop waits are interruptible by plugin disable.
- [x] Focused plugin lifecycle tests pass.
- [x] Compile verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

- Add `self._stop_event = threading.Event()` in each plugin constructor.
- Keep the existing `_start_scheduler()` / `_stop_scheduler()` helper structure.
- Use `self._stop_event.clear()` before starting and `self._stop_event.set()` before joining.
- Replace scheduler loop sleeps with `self._stop_event.wait(...)`.
- Keep joins short (`timeout=1`) to avoid blocking plugin disable.

## Out of Scope

- Do not change report generation, restart execution, route payloads, configs, or scheduler intervals.
- Do not refactor larger plugin worker flows in HDHive, HDHive sign, user backup, or one-off action threads.

## Verification Plan

- Compile: `uv run --with-requirements requirements.txt python -m compileall app/plugins/view_report/plugin.py app/plugins/emby_restart/plugin.py tests/test_plugin_scheduler_stop_events.py`.
- Focused tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/test_plugin_scheduler_stop_events.py -v`.
- Full tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v`.

## Verification Results

- `uv run --with-requirements requirements.txt --with pytest pytest tests/test_plugin_scheduler_stop_events.py -v`: 12 passed, 1 warning.
- `uv run --with-requirements requirements.txt python -m compileall app/plugins/view_report/plugin.py app/plugins/emby_restart/plugin.py tests/test_plugin_scheduler_stop_events.py`: passed.
- `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v`: 99 passed, 3 warnings.
- Search assertion: no remaining `time.sleep(...)`, raw scheduler-loop `Thread(...)`, `join(timeout=5)`, or `if self.scheduler_running` start guards in `view_report` / `emby_restart` scheduler lifecycle code.
