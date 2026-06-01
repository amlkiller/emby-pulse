# System Repair Schema Registry Usage

## Goal

Continue the P2 schema fact-source cleanup from `docs/架构审计.md` by making the system database repair helper reuse `app.infra.db.schema_registry` instead of maintaining a parallel set of handwritten core table DDL.

## Requirements

- Update `app.domains.system.system_tool_dao.repair_core_system_tables()` to create repair tables from `app.infra.db.schema_registry`.
- Preserve the public return type and existing user-facing result style: a list of Chinese repair/upgrade messages.
- Preserve repair behavior for the currently repaired core tables:
  - `PlaybackActivity`
  - `users_meta`
  - `invitations`
  - `tv_calendar_cache`
  - `media_requests`
  - `request_users`
  - `insight_ignores`
  - `gap_records`
- Apply registered schema ALTER statements for repaired/existing tables where `TABLE_ALTERS` covers them, ignoring duplicate-column errors as before.
- Do not change system database path resolution, route behavior, or dashboard layout persistence.
- Add focused regression coverage that proves the repair helper consumes schema registry definitions.

## Acceptance Criteria

- [x] `repair_core_system_tables()` imports and uses `TABLE_SCHEMAS`, `TABLE_ALTERS`, and `PLAYBACK_SCHEMA` from `app.infra.db.schema_registry`.
- [x] The repair helper no longer contains local multiline `CREATE TABLE` definitions for the repaired registry-owned tables.
- [x] Missing repaired tables are created with registry definitions.
- [x] Existing repaired tables receive applicable registered ALTER statements without failing on duplicate columns.
- [x] Focused system repair/schema registry tests pass.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

- Add a small local table-name/message mapping for the repaired table subset.
- For each repaired table, select `PLAYBACK_SCHEMA` for `PlaybackActivity` and `TABLE_SCHEMAS[table]` for system tables.
- Probe table existence with `SELECT 1 FROM <table> LIMIT 1`; create missing tables from registry SQL.
- Run applicable `TABLE_ALTERS[table]` statements after table creation/existence checks and ignore duplicate-column style `sqlite3.OperationalError`.
- Keep this slice focused on `system_tool_dao`; do not rewrite `app/infra/db/database.py` or domain/plugin DAO schema bootstrap code here.

## Out of Scope

- Do not consolidate `app/infra/db/database.py` `_create_system_tables()` in this slice.
- Do not migrate domain/plugin-specific schema declarations.
- Do not change schema SQL contents, table names, or ALTER list contents except where a behavior-preserving registry lookup requires it.
- Do not change API response payloads or route-level repair orchestration.

## Verification Plan

- Focused tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/test_system_repair_schema_registry.py -v`.
- Schema boundary tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/test_schema_registry_boundary.py -v`.
- Compile/import: `uv run --with-requirements requirements.txt python -m compileall app/domains/system/system_tool_dao.py tests/test_system_repair_schema_registry.py`.
- Full tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v`.

## Verification Results

- Passed: `$env:PYTHONIOENCODING='utf-8'; $env:UV_CACHE_DIR='.uv-cache'; uv run --with-requirements requirements.txt --with pytest pytest tests/test_system_repair_schema_registry.py -v`
- Passed: `$env:PYTHONIOENCODING='utf-8'; $env:UV_CACHE_DIR='.uv-cache'; uv run --with-requirements requirements.txt --with pytest pytest tests/test_schema_registry_boundary.py -v`
- Passed: `$env:PYTHONIOENCODING='utf-8'; $env:UV_CACHE_DIR='.uv-cache'; uv run --with-requirements requirements.txt python -m compileall app/domains/system/system_tool_dao.py tests/test_system_repair_schema_registry.py`
- Passed: `$env:PYTHONIOENCODING='utf-8'; $env:UV_CACHE_DIR='.uv-cache'; uv run --with-requirements requirements.txt --with pytest pytest tests/ -v` (`112 passed, 3 warnings`).
