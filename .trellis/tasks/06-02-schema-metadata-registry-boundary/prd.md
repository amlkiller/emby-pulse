# Schema Metadata Registry Boundary

## Goal

Continue the P2 schema fact-source cleanup from `docs/架构审计.md` by routing schema metadata consumers through the existing `app.infra.db.schema_registry` boundary.

## Requirements

- Remove the local `SYSTEM_TABLES` / `PLAYBACK_TABLES` duplicate definitions from `app/infra/db/database.py`.
- Change schema metadata consumers outside `schema_registry` to import from `app.infra.db.schema_registry` instead of `app.core.db_schemas`.
- Preserve database initialization, migration, health-check, and repair behavior.
- Keep `app.infra.db.schema_registry` as the only direct importer of `app.core.db_schemas` during this transitional slice.
- Add a focused regression test that prevents new direct schema metadata imports or local table-list duplicates.

## Acceptance Criteria

- [x] `app/infra/db/database.py` no longer defines its own `SYSTEM_TABLES` / `PLAYBACK_TABLES` lists.
- [x] `app/infra/db/db_manager.py` and `app/domains/system/system_tool_dao.py` consume schema metadata through `app.infra.db.schema_registry`.
- [x] `app.infra.db.schema_registry` is the only non-`app/core/db_schemas.py` file under `app/` that directly imports `app.core.db_schemas`.
- [x] Focused schema registry boundary tests pass.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

- Import `SYSTEM_TABLES` and `PLAYBACK_TABLES` from `app.infra.db.schema_registry` in `app/infra/db/database.py`.
- Import all schema metadata from `app.infra.db.schema_registry` in `app/infra/db/db_manager.py`.
- Import `SYSTEM_TABLES` from `app.infra.db.schema_registry` in `app/domains/system/system_tool_dao.py`.
- Add a small AST/text regression test under `tests/` for import and duplicate-list boundaries.

## Out of Scope

- Do not move the schema definitions out of `app/core/db_schemas.py` in this slice.
- Do not rewrite `_create_system_tables()` or change table DDL/ALTER behavior.
- Do not migrate plugin/domain DAO table declarations in this slice.

## Verification Plan

- Focused tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/test_schema_registry_boundary.py -v`.
- Compile/import: `uv run --with-requirements requirements.txt python -m compileall app/infra/db/schema_registry.py app/infra/db/database.py app/infra/db/db_manager.py app/domains/system/system_tool_dao.py tests/test_schema_registry_boundary.py`.
- Full tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v`.

## Verification Results

- `uv run --with-requirements requirements.txt --with pytest pytest tests/test_schema_registry_boundary.py -v`: 2 passed, 1 warning.
- `uv run --with-requirements requirements.txt python -m compileall app/infra/db/schema_registry.py app/infra/db/database.py app/infra/db/db_manager.py app/domains/system/system_tool_dao.py tests/test_schema_registry_boundary.py`: passed.
- `uv run --with-requirements requirements.txt python -c "from app.infra.db import database, db_manager, schema_registry; from app.domains.system import system_tool_dao; assert database.SYSTEM_TABLES is schema_registry.SYSTEM_TABLES; print('schema imports ok')"`: passed.
- `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v`: 107 passed, 3 warnings.
- Search assertion: app code has no direct `app.core.db_schemas` importer except `app/infra/db/schema_registry.py`, and `app/infra/db/database.py` no longer defines local `SYSTEM_TABLES` / `PLAYBACK_TABLES` lists.
