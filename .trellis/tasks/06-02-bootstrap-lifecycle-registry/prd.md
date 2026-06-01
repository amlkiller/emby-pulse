# Bootstrap Lifecycle Registry Slice

## Goal

Address the next P1 lifecycle item from `docs/架构审计.md` by introducing a small bootstrap service registry that centralizes service start/stop orchestration and prevents duplicate bootstrap starts in one process.

## Requirements

- Add a reusable bootstrap lifecycle registry for named services.
- Route `app/bootstrap/services.py` startup through the registry instead of direct ad hoc calls for every service.
- Preserve the existing startup order and user-facing startup/shutdown prints.
- Preserve current service behavior; do not rewrite domain loops, schedulers, or plugin lifecycle in this slice.
- Keep notification services as the only concrete stop hook for now, matching the current behavior.
- Make repeated `start_bootstrap_services(...)` calls idempotent for registered services in the same process.
- Make `stop_bootstrap_services()` call registered stop hooks in reverse startup order and reset registry state.
- Add focused tests for registry start idempotency, stop ordering, and bootstrap wiring.

## Acceptance Criteria

- [x] Bootstrap startup services are registered in one lifecycle registry.
- [x] Repeated bootstrap starts do not call registered start callbacks again while already started.
- [x] Stop callbacks run in reverse start order for services that define stops.
- [x] `stop_notification_services()` remains wired as the notification stop hook.
- [x] Startup order remains behavior-preserving.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

- Create `app/bootstrap/service_registry.py` with a small `BootstrapServiceRegistry`.
- Registry entries have `name`, `start`, and optional `stop` callbacks.
- `start_all()` starts entries in registration order and skips entries already marked started.
- `stop_all()` stops started entries in reverse order when they have a stop callback, then clears state.
- `app/bootstrap/services.py` builds the default registry for each `start_bootstrap_services(app, request_port)` call so request-port-specific callbacks stay explicit.
- Unit tests instantiate an isolated registry directly and monkeypatch bootstrap service callables for wiring checks.

## Out of Scope

- Do not add stop hooks to every domain service in this task.
- Do not change plugin scheduler lifecycle.
- Do not change `lifespan.py` or the app startup side effects beyond registry orchestration.
- Do not alter service thread implementations.

## Verification Plan

- Compile: `uv run --with-requirements requirements.txt python -m compileall app/bootstrap/service_registry.py app/bootstrap/services.py tests/test_bootstrap_lifecycle_registry.py`.
- Focused tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/test_bootstrap_lifecycle_registry.py -v`.
- Full tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v`.

## Verification Results

- Compile verification passed for bootstrap registry, services, and focused tests.
- Focused test passed: `tests/test_bootstrap_lifecycle_registry.py`, 3 tests.
- Full test suite passed: 77 passed, 3 warnings.
