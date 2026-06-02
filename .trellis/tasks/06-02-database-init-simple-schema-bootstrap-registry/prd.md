# Refactor database init simple table bootstraps through registry

## Problem

`app.infra.db.database` still contains many local `CREATE TABLE IF NOT EXISTS` statements for tables already owned by `app.infra.db.schema_registry`. This keeps the startup database initializer as a parallel schema fact source and extends the P2 issue called out in `docs/架构审计.md`.

## Scope

- Replace simple registry-owned table creation in `app.infra.db.database` with `schema_bootstrap.ensure_registered_table(...)`.
- Preserve local initialization for tables that are not yet registered or have complex migration semantics.
- Preserve existing index creation and post-init data repair behavior.
- Add focused tests proving database init now uses registry-backed bootstrap for the migrated table set and still creates those tables on a fresh database.
- Update backend database guidelines with the database-init subset contract.

## Out of Scope

- Media request rebuild migrations or other high-risk data-shape rewrites.
- Plugin table migration beyond existing registry-owned core tables.
- Broad cleanup of `app.infra.db.db_manager` or domain DAOs.

## Acceptance

- `database.py` no longer keeps local DDL for the selected simple registry-owned tables.
- Fresh `init_system_db()` creates the selected tables from the registry.
- Existing indexes and data-repair behavior remain in place.
- Focused tests, lint/compile/import checks, and the full pytest suite pass.
