# Bootstrap Service Stop Hooks Slice

## Goal

Continue the P1 lifecycle work from `docs/架构审计.md` by wiring concrete stop hooks for low-risk bootstrap-started services that already have clear stop semantics or simple background handles.

## Requirements

- Add and wire stop hooks for:
  - calendar notify service
  - system task poller
  - session cleanup loop
  - auth login-lock cleanup loop
- Preserve current startup behavior and startup order.
- Keep notification stop behavior unchanged.
- Do not refactor complex long-running domain loops in this slice:
  - risk monitor
  - media request community cache refresh
  - playback calendar background sync
  - user portal server
  - plugin schedulers
- Ensure stop hooks reset started state so services can restart in the same process.
- Add focused regression tests for the new stop hooks and registry wiring.

## Acceptance Criteria

- [x] `app/bootstrap/services.py` registers stop callbacks for calendar notify, system tasks, auth domain, and session services.
- [x] `stop_calendar_notify_services()` stops the calendar notify service.
- [x] `stop_system_task_services()` cancels and resets the poller task state.
- [x] `stop_auth_domain_services()` stops the login-lock cleanup loop and allows restart.
- [x] `stop_session_services()` stops the session cleanup loop and allows restart.
- [x] Focused lifecycle tests pass.
- [x] Compile verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

- Add stop functions next to the existing start functions in each owning module.
- For thread loops, use module-level `threading.Event` and thread handles so shutdown can signal the loop and reset started state.
- For the async system task poller, cancel the stored task and reset `_task_poller_started`.
- Wire stop callbacks into `build_bootstrap_registry(...)` without changing start order.

## Out of Scope

- Do not add stop hooks to risk/media/calendar/user-portal/plugin loops in this task.
- Do not change task polling semantics or notification payloads.
- Do not alter authentication/session table schemas.

## Verification Plan

- Compile: `uv run --with-requirements requirements.txt python -m compileall app/bootstrap/services.py app/domains/notifications/calendar_notify.py app/domains/system/tasks.py app/domains/users/auth.py app/core/session.py tests/test_bootstrap_stop_hooks.py tests/test_bootstrap_lifecycle_registry.py`.
- Focused tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/test_bootstrap_stop_hooks.py tests/test_bootstrap_lifecycle_registry.py -v`.
- Full tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v`.

## Verification Results

- Compile verification passed for changed lifecycle modules and focused tests.
- Focused lifecycle tests passed: 7 tests.
- Full test suite passed: 81 passed, 3 warnings.
