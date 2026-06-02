# Remove pro startup redirect

## Goal

Remove `start_pro_services()`, which only redirects to `ensure_pro_schema()` without adding behavior.

## Scope

- Register `ensure_pro_schema` directly in bootstrap services.
- Delete `start_pro_services` from `app.domains.system.pro`.
- Update bootstrap lifecycle tests to patch the real startup function.

## Non-Goals

- Do not change Pro schema initialization, logging, or error handling.
- Do not clean configuration, environment, variable, DAO SQL, or simple accessor functions.
- Do not remove wrappers that adapt parameters, enforce boundaries, or perform orchestration.

## Acceptance

- `start_pro_services` no longer appears under `app/` or `tests/`.
- Focused compile/import checks pass.
- Focused bootstrap lifecycle tests pass.
- Full `uv run pytest tests/ -v` passes with UTF-8 output on Windows.
