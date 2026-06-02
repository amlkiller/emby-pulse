# Session Schema Registry Bootstrap

## Goal

Continue the architecture audit schema-source refactor by moving the persisted `sessions` table definition out of `app.infra.db.session_dao` and into the shared schema registry.

## Requirements

- Register `sessions` as a system database table in `app.infra.db.schema_registry`.
- Route `app.infra.db.session_dao.ensure_session_table()` through `schema_bootstrap.ensure_registered_table(...)`.
- Keep the `idx_sessions_expires` index creation local to `session_dao` because index metadata is not centralized yet.
- Preserve existing session create/get/update/delete/clear/cleanup behavior.
- Add focused regression tests for fresh bootstrap, index preservation, DAO smoke paths, clear-if-exists behavior, and absence of local duplicate session table DDL.
- Update backend database spec guidance to document the `sessions` registry boundary.

## Acceptance Criteria

- `sessions` appears in `SYSTEM_TABLES` and `TABLE_SCHEMAS`.
- `ensure_session_table()` creates the table through `ensure_registered_table(cursor, "sessions")`.
- `session_dao` no longer contains local `CREATE TABLE IF NOT EXISTS sessions` DDL.
- `idx_sessions_expires` is still created by `ensure_session_table()`.
- Session DAO create/get/update/delete/clear/cleanup paths work against a temporary system database.
- Focused tests, compile, ruff, `git diff --check`, and full pytest pass in one consolidated verification pass.

## Out of Scope

- Do not change cookie/session middleware behavior.
- Do not change session expiration policy or cleanup loop lifecycle.
- Do not centralize index metadata in this slice.
- Do not refactor `app.core.session` beyond preserving current DAO calls.

## Technical Notes

- Audit reference: `docs/架构审计.md` P2 issue 4, schema fact source split.
- Existing table owner: `app.infra.db.session_dao`.
- Existing shared helper: `app.infra.db.schema_bootstrap.ensure_registered_table(...)`.
- `sessions` uses `system_store`, so it belongs to system DB schema metadata.
