# Dedupe Schema Bootstrap Registry

## Goal

Continue the P2 schema fact-source cleanup from `docs/架构审计.md` by routing `app.domains.playback.dedupe_dao.init_dedupe_tables()` through `app.infra.db.schema_registry` for registry-owned dedupe tables.

## Requirements

- Update `init_dedupe_tables()` to create these registry-owned tables from `TABLE_SCHEMAS`:
  - `dedupe_whitelist`
  - `dedupe_results`
  - `dedupe_config`
- Apply registered `TABLE_ALTERS["dedupe_results"]` so existing partial `dedupe_results` tables receive all additive fields.
- Apply compatible registered `TABLE_ALTERS["dedupe_whitelist"]` for existing non-legacy whitelist tables that lack `title`.
- Preserve the legacy `dedupe_whitelist` migration behavior when an old table has `id` and lacks `group_key`, including carrying `item_id` to `group_key`, `item_name` to `title`, and preserving `created_at`.
- Preserve public DAO function names and existing read/write behavior.
- Add focused regression coverage proving the dedupe bootstrap consumes registry definitions and no longer contains local duplicate dedupe table DDL or local dedupe ALTER maps.

## Acceptance Criteria

- [x] `dedupe_dao.init_dedupe_tables()` imports and uses `TABLE_SCHEMAS` from `app.infra.db.schema_registry`.
- [x] `dedupe_dao.init_dedupe_tables()` imports and uses `TABLE_ALTERS` for `dedupe_results` and compatible `dedupe_whitelist` alters.
- [x] `dedupe_dao.init_dedupe_tables()` contains no local `CREATE TABLE IF NOT EXISTS dedupe_results`, `dedupe_whitelist`, or `dedupe_config` DDL.
- [x] Missing dedupe tables are created from registry definitions.
- [x] Existing partial `dedupe_results` tables receive registered additive columns idempotently.
- [x] Legacy `dedupe_whitelist` tables are still migrated to the registry shape with data preserved.
- [x] Focused dedupe schema bootstrap tests pass.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

- Import `TABLE_SCHEMAS` and `TABLE_ALTERS` from `app.infra.db.schema_registry`.
- Define the dedupe table list locally as the subset this DAO bootstraps.
- Keep the legacy whitelist shape detection before normal registry creation.
- Recreate migrated legacy `dedupe_whitelist` using `TABLE_SCHEMAS["dedupe_whitelist"]`.
- Loop the remaining dedupe table list and execute `TABLE_SCHEMAS[table]`.
- Loop `TABLE_ALTERS.get("dedupe_results", [])` and `TABLE_ALTERS.get("dedupe_whitelist", [])`, ignoring duplicate-column `sqlite3.OperationalError`.
- Use temp database tests by monkeypatching `system_store.db_path`.

## Out of Scope

- Do not refactor `app.domains.media_requests.media_request_dao.ensure_media_request_schema()` in this slice.
- Do not modify `app/infra/db/database.py` bootstrap blocks in this slice.
- Do not change dedupe route behavior, scan scoring, whitelist API payloads, config format, or DAO query return shapes.
- Do not add new dedupe schema fields.

## Verification Plan

- Focused tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/test_dedupe_schema_bootstrap_registry.py -v`.
- Schema boundary tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/test_schema_registry_boundary.py tests/test_small_schema_bootstraps_registry.py tests/test_system_repair_schema_registry.py tests/test_gap_schema_bootstrap_registry.py -v`.
- Compile/import: `uv run --with-requirements requirements.txt python -m compileall app/domains/playback/dedupe_dao.py tests/test_dedupe_schema_bootstrap_registry.py`.
- Full tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v`.

## Verification Results

- Focused tests: `5 passed, 1 warning`.
- Schema registry regression batch: `20 passed, 1 warning`.
- Compile/import: passed for `app/domains/playback/dedupe_dao.py` and `tests/test_dedupe_schema_bootstrap_registry.py`.
- Ruff changed files: passed.
- Full tests: `125 passed, 3 warnings`.
- `git diff --check`: passed.
