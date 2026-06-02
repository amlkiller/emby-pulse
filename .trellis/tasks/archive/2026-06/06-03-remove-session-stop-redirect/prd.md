# Remove session stop redirect

## Goal

Remove `stop_session_services()`, which only redirects to `stop_session_cleanup_loop()` without adding behavior.

## Scope

- Register `stop_session_cleanup_loop` directly in bootstrap services.
- Update tests that call or monkeypatch `stop_session_services` to use `stop_session_cleanup_loop`.
- Delete `stop_session_services` from `app.core.session`.

## Non-Goals

- Do not remove or change `start_session_services`; it performs initialization plus cleanup-loop startup.
- Do not clean configuration, environment, variable, or simple accessor getters.
- Do not change session persistence or cleanup-loop behavior.

## Acceptance

- `stop_session_services` no longer appears under `app/` or `tests/`.
- Focused compile/import checks pass.
- Focused stop-hook and bootstrap lifecycle tests pass.
- Full `uv run pytest tests/ -v` passes with UTF-8 output on Windows.
