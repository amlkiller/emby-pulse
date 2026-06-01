# Gap Schema Bootstrap Registry

## Goal

Continue the P2 schema fact-source cleanup from `docs/架构审计.md` by routing `app.domains.media_requests.gap_dao.ensure_gap_tables()` through `app.infra.db.schema_registry` for registry-owned gap tables.

## Requirements

- Update `ensure_gap_tables()` to create these registry-owned tables from `TABLE_SCHEMAS`:
  - `gap_config`
  - `gap_records`
  - `gap_perfect_series`
  - `gap_scan_cache`
- Apply registered `TABLE_ALTERS["gap_perfect_series"]` so `tmdb_id` remains covered for existing tables.
- Preserve the default `gap_config.cache_interval_hours = 6` initialization.
- Preserve the legacy `gap_scan_cache` migration behavior when an old table has `series_id` but lacks `result_json`.
- Preserve public DAO function names and existing read/write behavior.
- Add focused regression coverage proving the gap bootstrap consumes registry definitions and no longer contains local duplicate gap table DDL.

## Acceptance Criteria

- [x] `gap_dao.ensure_gap_tables()` imports and uses `TABLE_SCHEMAS` from `app.infra.db.schema_registry`.
- [x] `gap_dao.ensure_gap_tables()` imports and uses `TABLE_ALTERS` for `gap_perfect_series`.
- [x] `gap_dao.ensure_gap_tables()` contains no local `CREATE TABLE IF NOT EXISTS gap_config`, `gap_records`, `gap_perfect_series`, or `gap_scan_cache` DDL.
- [x] Missing gap tables are created from registry definitions.
- [x] Existing `gap_perfect_series` tables receive the registered `tmdb_id` ALTER without failing on duplicate columns.
- [x] Legacy `gap_scan_cache` tables are still migrated to the registry shape.
- [x] Focused gap schema bootstrap tests pass.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

- Import `TABLE_SCHEMAS` and `TABLE_ALTERS` from `app.infra.db.schema_registry`.
- Define the gap table list locally as the subset this DAO bootstraps.
- Loop the gap table list and execute `TABLE_SCHEMAS[table]`.
- Loop `TABLE_ALTERS.get("gap_perfect_series", [])`, ignoring duplicate-column `sqlite3.OperationalError`.
- Replace the legacy `gap_scan_cache` recreation SQL with `TABLE_SCHEMAS["gap_scan_cache"]`.
- Use temp database tests by monkeypatching `system_store.db_path`.

## Out of Scope

- Do not modify `app/infra/db/database.py` bootstrap blocks in this slice.
- Do not refactor `media_request_dao.ensure_media_request_schema()` or `dedupe_dao.init_dedupe_tables()` in this slice.
- Do not change gap route behavior, cache payload format, or DAO query return shapes.
- Do not add new gap schema fields.

## Verification Plan

- Focused tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/test_gap_schema_bootstrap_registry.py -v`.
- Schema boundary tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/test_schema_registry_boundary.py tests/test_small_schema_bootstraps_registry.py tests/test_system_repair_schema_registry.py -v`.
- Compile/import: `uv run --with-requirements requirements.txt python -m compileall app/domains/media_requests/gap_dao.py tests/test_gap_schema_bootstrap_registry.py`.
- Full tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v`.

## Verification Results

- Focused tests: `4 passed, 1 warning`.
- Schema registry regression batch: `15 passed, 1 warning`.
- Compile/import: passed for `app/domains/media_requests/gap_dao.py` and `tests/test_gap_schema_bootstrap_registry.py`.
- Ruff changed files: passed.
- Full tests: `120 passed, 3 warnings`.
- Active PRD checkbox sweep: all active PRDs have zero unchecked acceptance items after this update.
