# Audit Logger Schema Registry Bootstrap

## Goal

Continue the architecture audit schema-source refactor by moving the `audit_logs` table definition out of `app.infra.db.audit_logger_dao` and into the shared schema registry.

## Requirements

- Register `audit_logs` as a system database table in `app.infra.db.schema_registry`.
- Route `app.infra.db.audit_logger_dao.ensure_audit_table()` through the shared registry-backed bootstrap helper.
- Keep audit-log index creation local to `audit_logger_dao` because index metadata is not centralized in this refactor line yet.
- Preserve existing audit log insert, list, stats, and cleanup behavior.
- Add focused regression tests that prove fresh bootstrap, DAO smoke paths, and no local duplicate audit table DDL remain.
- Update backend database spec guidance to capture the `audit_logs` registry boundary.

## Acceptance Criteria

- `audit_logs` appears in `SYSTEM_TABLES` and `TABLE_SCHEMAS`.
- `ensure_audit_table()` creates `audit_logs` through `schema_bootstrap.ensure_registered_table(...)`.
- `audit_logger_dao` no longer contains a local `CREATE TABLE IF NOT EXISTS audit_logs` string.
- Audit-log indexes (`idx_audit_timestamp`, `idx_audit_user_id`, `idx_audit_action`) are still created.
- Inserting, listing, stats, and cleanup work against a temporary system database.
- Focused tests, compile, ruff, `git diff --check`, and full pytest pass in one consolidated verification pass.

## Out of Scope

- Do not change audit route/API response payloads.
- Do not merge `audit_logs` with `user_audit_logs`.
- Do not centralize index metadata in this slice.
- Do not refactor `app.core.audit_logger` beyond preserving current DAO calls.

## Technical Notes

- Audit reference: `docs/架构审计.md` P2 issue 4, schema fact source split.
- Existing table owner: `app.infra.db.audit_logger_dao`.
- Existing shared helper: `app.infra.db.schema_bootstrap.ensure_registered_table(...)`.
- `audit_logs` uses `system_store`, so it belongs to system DB schema metadata rather than playback schema metadata.
