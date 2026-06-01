# Bootstrap Long Loop Stop Hooks

## Goal

Continue the P1 lifecycle work from `docs/架构审计.md` by adding stop hooks to the remaining low-to-medium risk bootstrap-started long loops.

## Requirements

- Add and wire stop hooks for:
  - risk monitor loop
  - media request community cache refresh loop
  - playback calendar background sync loop
- Preserve current startup behavior and startup order.
- Keep existing idempotent start behavior.
- Stop hooks must reset started state so services can restart in the same process.
- Loop sleeps must use stop events instead of uninterruptible `time.sleep(...)`.
- Do not refactor user portal server lifecycle in this task.
- Do not refactor plugin scheduler lifecycle in this task.
- Add focused regression tests for stop/restart behavior and bootstrap registry wiring.

## Acceptance Criteria

- [x] `app/bootstrap/services.py` registers stop callbacks for risk monitor, media request services, and playback calendar services.
- [x] `stop_risk_monitor()` stops the risk monitor loop and resets started state.
- [x] `stop_media_request_services()` stops the community cache refresh loop and resets started state.
- [x] `stop_calendar_service()` stops the playback calendar background sync loop and resets started state.
- [x] Focused lifecycle tests pass.
- [x] Compile verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

- Add module-level `threading.Event` and thread handles for module-level loops.
- Add instance-level stop event and thread handle for `CalendarService`.
- Use `Event.wait(...)` for sleep intervals so stop hooks can interrupt long waits.
- Keep initial delay and refresh intervals unchanged.
- Wire stop callbacks into `build_bootstrap_registry(...)` without changing start order.

## Out of Scope

- Do not change user portal uvicorn lifecycle.
- Do not change plugin scheduler lifecycle.
- Do not alter risk/media/calendar business logic or notification payloads.

## Verification Plan

- Compile: `uv run --with-requirements requirements.txt python -m compileall app/bootstrap/services.py app/domains/risk/risk_service.py app/domains/media_requests/router.py app/domains/playback/calendar_service.py tests/test_bootstrap_long_loop_stop_hooks.py tests/test_bootstrap_lifecycle_registry.py`.
- Focused tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/test_bootstrap_long_loop_stop_hooks.py tests/test_bootstrap_lifecycle_registry.py -v`.
- Full tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v`.

## Verification Results

- Compile verification passed for changed lifecycle modules and focused tests.
- Focused lifecycle tests passed: 6 tests.
- Full test suite passed: 84 passed, 3 warnings.
