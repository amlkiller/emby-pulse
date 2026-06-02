# Dashboard Cache Stop Hook

## Goal

Continue the architecture audit lifecycle refactor by making the bootstrap-started dashboard cache background refresh task stoppable and restartable in the same process.

## Requirements

- Add a `stop_dashboard_cache_tasks()` hook next to `start_dashboard_cache_tasks()` in `app.domains.playback.stats`.
- Save asyncio task handles for the dashboard preload task and refresh-loop task.
- Make the dashboard refresh loop cancellable without waiting for the old endless `asyncio.sleep(60)` loop.
- Ensure stop resets `_dashboard_cache_tasks_started` and clears task handles so a later start works in the same process.
- Route `app.bootstrap.services` `"dashboard-cache"` registration through paired start/stop callbacks.
- Preserve dashboard cache data shape, API responses, cache TTL logic, and preload behavior.
- Add focused regression tests for stop/restart behavior and bootstrap registry stop registration.

## Acceptance Criteria

- `start_dashboard_cache_tasks()` remains idempotent.
- `stop_dashboard_cache_tasks()` cancels saved dashboard preload/refresh tasks and resets module state.
- Restarting after stop works in the same event loop/process.
- `build_bootstrap_registry(...)` registers `"dashboard-cache"` with both start and stop callbacks.
- Focused lifecycle tests, compile, ruff, `git diff --check`, and full pytest pass in one consolidated verification pass.

## Out of Scope

- Do not change dashboard route payloads or cache-key behavior.
- Do not change `_fetch_dashboard_core(...)`, `_fetch_users_list(...)`, or other dashboard query logic.
- Do not refactor playback stats routing or split the large `stats.py` file in this slice.
- Do not change plugin scheduler lifecycle in this slice.

## Technical Notes

- Audit reference: `docs/架构审计.md` P1 issue 3, lifecycle management incomplete.
- Existing lifecycle spec: `.trellis/spec/backend/directory-structure.md`.
- Existing pattern references: `app.domains.system.tasks.stop_system_task_services()` and `tests/test_bootstrap_stop_hooks.py`.
