# User Portal Lifecycle Stop Hook

## Goal

Continue the P1 lifecycle work from `docs/架构审计.md` by adding a concrete stop hook for the isolated user portal server started by bootstrap.

## Requirements

- Preserve current user portal route filtering and startup behavior.
- Make `start_user_portal_thread(app, request_port)` idempotent while a portal thread is alive.
- Save the uvicorn server and thread handles needed for shutdown.
- Add `stop_user_portal_thread()` that requests uvicorn shutdown, joins the thread briefly, and clears stopped handles.
- Wire `stop_user_portal_thread()` into the bootstrap lifecycle registry.
- Add focused tests for idempotent start, stop handle reset, and bootstrap registry wiring.

## Acceptance Criteria

- [x] `app/bootstrap/services.py` registers `stop_user_portal_thread` for the `user-portal` service.
- [x] Repeated `start_user_portal_thread(...)` calls do not start multiple live portal threads.
- [x] `stop_user_portal_thread()` sets `server.should_exit = True` when a server handle exists.
- [x] `stop_user_portal_thread()` clears stopped thread/server handles.
- [x] Focused tests pass.
- [x] Compile verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

- Keep `start_user_portal_server(...)` as the thread target.
- Add module-level lock, thread handle, and uvicorn server handle.
- Register the server handle immediately before `server.serve(...)` and clear it in `finally`.
- Use `thread.join(timeout=1)` during stop to avoid blocking shutdown indefinitely.
- Preserve current socket binding behavior: if the port is unavailable, return without raising.

## Out of Scope

- Do not change allowed/blocked user portal route lists.
- Do not change main app lifespan behavior.
- Do not refactor plugin scheduler lifecycle.

## Verification Plan

- Compile: `uv run --with-requirements requirements.txt python -m compileall app/bootstrap/user_portal.py app/bootstrap/services.py tests/test_user_portal_lifecycle.py tests/test_bootstrap_lifecycle_registry.py`.
- Focused tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/test_user_portal_lifecycle.py tests/test_bootstrap_lifecycle_registry.py -v`.
- Full tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v`.

## Verification Results

- Compile verification passed for user portal lifecycle modules and focused tests.
- Focused lifecycle tests passed: 6 tests.
- Full test suite passed: 87 passed, 3 warnings.
