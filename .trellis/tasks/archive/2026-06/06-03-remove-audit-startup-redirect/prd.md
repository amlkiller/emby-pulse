# Remove audit startup redirect

## Goal

Remove `start_audit_services()`, which only redirects to `init_audit_table()` without adding behavior.

## Scope

- Register `init_audit_table` directly in bootstrap services.
- Delete `start_audit_services` from `app.core.audit_logger`.
- Update bootstrap lifecycle tests to patch/assert the real startup function.

## Non-Goals

- Do not change audit table initialization behavior, logging, or DAO calls.
- Do not clean getter/accessor functions that only read configuration or variables.

## Acceptance

- `start_audit_services` no longer appears under `app/` or `tests/`.
- Focused compile/import checks pass.
- Full test suite passes through `uv run`.
