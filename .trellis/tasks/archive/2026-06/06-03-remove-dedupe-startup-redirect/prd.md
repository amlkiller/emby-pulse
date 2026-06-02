# Remove dedupe startup redirect

## Goal

Remove `start_dedupe_services()`, which only redirects to `init_dedupe_db()` without adding behavior.

## Scope

- Register `init_dedupe_db` directly in bootstrap services.
- Delete `start_dedupe_services` from `app.domains.playback.dedupe`.
- Update bootstrap lifecycle tests to patch the real startup function.

## Non-Goals

- Do not change dedupe table initialization, logging, or error handling.
- Do not clean configuration, environment, variable, DAO SQL, or simple accessor functions.
- Do not remove wrappers that adapt parameters, enforce boundaries, or perform orchestration.

## Acceptance

- `start_dedupe_services` no longer appears under `app/` or `tests/`.
- Focused compile/import checks pass.
- Focused bootstrap lifecycle tests pass.
- Full `uv run pytest tests/ -v` passes with UTF-8 output on Windows.
