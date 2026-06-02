# DB Manager Migration Schema Bootstrap Convergence

## Goal

Route `app.infra.db.db_manager.migrate_tables()` target table creation through the shared registry bootstrap helper so migrated system tables receive registry-owned compatible columns and simple indexes consistently.

## Requirements

* Keep migration behavior and result payloads stable for incremental and overwrite modes.
* When migrating a registry-owned system table, create or upgrade the destination table with `schema_bootstrap.ensure_registered_table(...)` instead of executing raw `TABLE_SCHEMAS[table]`.
* Preserve source-table fallback DDL for any future non-registry table that is explicitly allowed through the migration path.
* Add focused tests that prove migration applies registered `TABLE_ALTERS` and `TABLE_INDEXES` to the destination schema.

## Acceptance Criteria

* [ ] `migrate_tables()` uses the shared schema bootstrap helper for registry-owned table targets.
* [ ] A focused test migrates a table with a registered ALTER and verifies the added column exists.
* [ ] A focused test migrates a table with a registered index and verifies the index exists.
* [ ] Compile checks, focused pytest, and full pytest pass through `uv run`.

## Definition of Done

* Tests added/updated where the behavior is covered.
* `uv run python -m compileall` passes for changed Python files.
* Focused pytest passes.
* Full `uv run pytest tests/ -v` passes before completion.
* Task work is committed before Trellis archive/journal commits.

## Technical Approach

Import `ensure_registered_table` from `app.infra.db.schema_bootstrap` in `db_manager.py` and use it in `migrate_tables()` when the requested table exists in `TABLE_SCHEMAS`. Add temporary SQLite migration tests by monkeypatching `db_manager.DB_PATH` and `db_manager.SYSTEM_DB_PATH`.

## Decision (ADR-lite)

Context: schema registry convergence has already moved DAO/local bootstraps to `schema_bootstrap.ensure_registered_table(...)`, but `migrate_tables()` still creates destination tables from raw registry DDL.

Decision: make migration target creation use the same helper while leaving broader `db_manager.ensure_tables()` repair behavior for a separate, higher-risk slice.

Consequences: migration receives registry ALTER/index behavior without changing migration row copy logic. Remaining direct registry metadata usage in `db_manager` is intentionally not removed in this task.

## Out of Scope

* Refactoring `db_manager.ensure_tables()` repair/rebuild behavior.
* Changing `system_tool_dao.repair_core_system_tables()` repair message semantics.
* Wrapper/pass-through cleanup.
* Broad lifecycle loop refactors.

## Technical Notes

* Relevant files inspected: `app/infra/db/db_manager.py`, `app/infra/db/schema_bootstrap.py`, `app/infra/db/schema_registry.py`.
* Backend specs read: `.trellis/spec/backend/database-guidelines.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/guides/index.md`.
* Windows verification commands that import project modules may need `PYTHONIOENCODING=utf-8`.
