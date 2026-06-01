# Small Schema Bootstraps Registry

## Goal

Continue the P2 schema fact-source cleanup from `docs/架构审计.md` by routing small registry-owned schema bootstrap helpers through `app.infra.db.schema_registry` instead of keeping local duplicate DDL.

## Requirements

- Update `app.infra.db.notification_dao.ensure_notifications_table()` to create `sys_notifications` from `TABLE_SCHEMAS["sys_notifications"]`.
- Update `ensure_notifications_table()` to apply `TABLE_ALTERS["sys_notifications"]` instead of a local handwritten `ALTER TABLE` statement.
- Update `app.domains.system.system_tool_dao` dashboard layout helpers to create `sys_dashboard` from `TABLE_SCHEMAS["sys_dashboard"]`.
- Preserve public function names, return behavior, and existing notification/dashboard behavior.
- Add focused regression coverage proving the two bootstrap helpers consume registry definitions and no longer contain local duplicate `CREATE TABLE` DDL for registry-owned tables.

## Acceptance Criteria

- [x] `notification_dao.ensure_notifications_table()` imports and uses `TABLE_SCHEMAS` and `TABLE_ALTERS` from `app.infra.db.schema_registry`.
- [x] `notification_dao.ensure_notifications_table()` contains no local `CREATE TABLE IF NOT EXISTS sys_notifications` or local `ALTER TABLE sys_notifications ADD COLUMN is_cleared` SQL.
- [x] `system_tool_dao` dashboard layout helpers use `TABLE_SCHEMAS["sys_dashboard"]`.
- [x] `system_tool_dao` contains no local `CREATE TABLE IF NOT EXISTS sys_dashboard` SQL.
- [x] Focused small schema bootstrap tests pass.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Results

- Implemented notification and dashboard layout bootstraps through `app.infra.db.schema_registry`.
- Added focused temp database regression coverage in `tests/test_small_schema_bootstraps_registry.py`.
- Passed focused verification: `uv run --with-requirements requirements.txt --with pytest pytest tests/test_small_schema_bootstraps_registry.py -v`.
- Passed schema boundary verification: `uv run --with-requirements requirements.txt --with pytest pytest tests/test_schema_registry_boundary.py tests/test_system_repair_schema_registry.py -v`.
- Passed ruff verification: `uv run --with-requirements requirements.txt --with ruff ruff check app/infra/db/notification_dao.py app/domains/system/system_tool_dao.py tests/test_small_schema_bootstraps_registry.py`.
- Passed compile verification: `uv run --with-requirements requirements.txt python -m compileall app/infra/db/notification_dao.py app/domains/system/system_tool_dao.py tests/test_small_schema_bootstraps_registry.py`.
- Passed full test suite: `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v` (`116 passed, 3 warnings`).

## Technical Approach

- Import schema metadata from `app.infra.db.schema_registry`.
- Execute registry `CREATE TABLE` SQL for `sys_notifications` and `sys_dashboard`.
- Loop registry ALTER statements for `sys_notifications`, ignoring duplicate-column `sqlite3.OperationalError`.
- Execute registry `CREATE TABLE` SQL for `sys_dashboard` before dashboard layout reads/writes.
- Use temp database tests by monkeypatching `system_store.db_path`.

## Out of Scope

- Do not modify `app/infra/db/database.py` bootstrap blocks in this slice.
- Do not migrate session, audit, plugin, or domain-specific tables that are not currently registry-owned.
- Do not modify `app.domains.system.pro_license_dao` in this slice; `sys_license` has local extension columns that need a separate schema decision.
- Do not change notification or dashboard layout API response shapes.

## Verification Plan

- Focused tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/test_small_schema_bootstraps_registry.py -v`.
- Schema boundary tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/test_schema_registry_boundary.py tests/test_system_repair_schema_registry.py -v`.
- Compile/import: `uv run --with-requirements requirements.txt python -m compileall app/infra/db/notification_dao.py app/domains/system/system_tool_dao.py tests/test_small_schema_bootstraps_registry.py`.
- Full tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v`.
