# Move Schema Definitions To Infra Registry

## Goal

Continue the P2 schema fact-source cleanup from `docs/架构审计.md` by moving the actual schema metadata definitions from `app/core/db_schemas.py` into `app/infra/db/schema_registry.py`.

## Requirements

- Make `app.infra.db.schema_registry` own the actual schema metadata definitions:
  - `SYSTEM_TABLES`
  - `PLAYBACK_TABLES`
  - `TABLE_SCHEMAS`
  - `TABLE_ALTERS`
  - `CORE_TABLES`
  - `PLAYBACK_SCHEMA`
- Keep `app.core.db_schemas` as a thin compatibility re-export during the transition.
- Preserve all exported names and object values.
- Preserve database initialization, migration, health-check, and repair behavior.
- Update focused schema boundary tests to prove the ownership direction changed.

## Acceptance Criteria

- [x] `app/infra/db/schema_registry.py` contains the schema metadata definitions.
- [x] `app/core/db_schemas.py` contains no local schema metadata list/dict/string definitions and only re-exports from `app.infra.db.schema_registry`.
- [x] No app code outside `app/core/db_schemas.py` imports schema metadata from `app.core.db_schemas`.
- [x] Compatibility imports from `app.core.db_schemas` still expose the same objects as `app.infra.db.schema_registry`.
- [x] Focused schema registry boundary tests pass.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

- Move the body of `app/core/db_schemas.py` into `app/infra/db/schema_registry.py`.
- Replace `app/core/db_schemas.py` with a compatibility module importing/exporting the same symbols from `schema_registry`.
- Update `tests/test_schema_registry_boundary.py` to assert the new ownership direction and compatibility identity.
- Keep this as a mechanical ownership move: no table DDL, ALTER list, or runtime behavior changes.

## Out of Scope

- Do not rewrite `_create_system_tables()` in `app/infra/db/database.py`.
- Do not change any schema SQL, table list contents, ALTER list contents, migration behavior, or repair behavior.
- Do not migrate domain/plugin-specific table declarations in this slice.

## Verification Plan

- Focused tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/test_schema_registry_boundary.py -v`.
- Compile/import: `uv run --with-requirements requirements.txt python -m compileall app/infra/db/schema_registry.py app/core/db_schemas.py tests/test_schema_registry_boundary.py`.
- Import identity: `uv run --with-requirements requirements.txt python -c "from app.infra.db import schema_registry; from app.core import db_schemas; assert db_schemas.SYSTEM_TABLES is schema_registry.SYSTEM_TABLES; print('schema ownership ok')"`.
- Full tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v`.

## Verification Results

- Focused tests passed: `4 passed, 1 warning`.
- Compile verification passed for `app/infra/db/schema_registry.py`, `app/core/db_schemas.py`, and `tests/test_schema_registry_boundary.py`.
- Import identity verification passed and printed `schema ownership ok`.
- Import scan passed: no app module outside `app/core/db_schemas.py` imports `app.core.db_schemas`.
- Full test suite passed: `109 passed, 3 warnings`.
