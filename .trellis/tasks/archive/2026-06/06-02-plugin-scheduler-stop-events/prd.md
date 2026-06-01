# Plugin Scheduler Stop Events Slice

## Goal

Continue the P1 lifecycle work from `docs/架构审计.md` by making a first batch of plugin scheduler loops interruptible and restart-safe.

## Requirements

- Add stop-event based lifecycle control for plugins that use the same `_running + thread + sleep loop` pattern:
  - `auto_expire`
  - `temp_account`
  - `keep_alive`
  - `smart_collections`
- Preserve plugin enable/disable behavior and user-facing logs.
- Keep scheduler intervals and business logic unchanged.
- Make `on_enable()` idempotent while the scheduler thread is alive.
- Make `on_disable()` signal the scheduler, join briefly, clear thread handles, and allow later re-enable.
- Replace long `time.sleep(...)` waits in scheduler loops with interruptible `Event.wait(...)`.
- Add focused regression tests for stop/restart behavior.

## Acceptance Criteria

- [x] The four target plugins each have a stop event and saved thread handle lifecycle.
- [x] The four target plugins skip duplicate scheduler starts while a thread is alive.
- [x] The four target plugins clear thread handles on disable.
- [x] Long scheduler waits are interruptible by plugin disable.
- [x] Focused plugin lifecycle tests pass.
- [x] Compile verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

- Add `self._stop_event = threading.Event()` in each plugin constructor.
- Add small private `_start_*` / `_stop_*` helpers where useful, or keep logic in `on_enable` / `on_disable` if local style is simpler.
- Use `self._stop_event.clear()` before starting and `self._stop_event.set()` before joining.
- Replace startup delays and interval sleeps with `self._stop_event.wait(...)`.
- Keep joins short (`timeout=1`) to avoid blocking plugin disable.

## Out of Scope

- Do not change plugin route payloads, configs, or scheduler intervals.
- Do not refactor plugins with different scheduler styles in this task, such as view reports, Emby restart, HDHive, HDHive sign, user backup, or plugin-specific worker threads.

## Verification Plan

- Compile: `uv run --with-requirements requirements.txt python -m compileall app/plugins/auto_expire/plugin.py app/plugins/temp_account/plugin.py app/plugins/keep_alive/plugin.py app/plugins/smart_collections/plugin.py tests/test_plugin_scheduler_stop_events.py`.
- Focused tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/test_plugin_scheduler_stop_events.py -v`.
- Full tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v`.

## Verification Results

- `uv run --with-requirements requirements.txt --with pytest pytest tests/test_plugin_scheduler_stop_events.py -v`: 8 passed, 1 warning.
- `uv run --with-requirements requirements.txt python -m compileall app/plugins/auto_expire/plugin.py app/plugins/temp_account/plugin.py app/plugins/keep_alive/plugin.py app/plugins/smart_collections/plugin.py tests/test_plugin_scheduler_stop_events.py`: passed.
- `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v`: 95 passed, 3 warnings.
- Active PRD aggregate scan: current plugin scheduler PRD was the only active PRD with unchecked acceptance criteria before this update; other active PRDs remained out of scope for this commit.
