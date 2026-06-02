# Schema Index Fact-Source Convergence

## Goal

Continue the architecture audit P2 schema convergence work by moving remaining registered index DDL out of bootstrap/DAO ad hoc execution and into the shared schema registry/bootstrap path.

## Requirements

- Add a registry-owned place for table index DDL so table creation, alters, and indexes share one schema fact source.
- Extend `schema_bootstrap` helpers so registered table bootstraps can apply their registered indexes.
- Move the currently duplicated/simple registered index statements for core tables and DAO-owned tables into the registry.
- Preserve behavior for existing schema creation, safe registered alters, repair/database initialization, and DAO smoke paths.
- Keep compatibility migration logic that is not simple registry-owned DDL, such as legacy table rebuild/rename/drop code, in its current owner.
- Do one consolidated verification pass and one work commit for this task.

## Acceptance Criteria

- `TABLE_INDEXES` or equivalent registry metadata exists beside `TABLE_SCHEMAS` / `TABLE_ALTERS`.
- `ensure_registered_table(...)` applies indexes by default after CREATE/ALTER.
- `ensure_playback_table(...)` applies registered playback indexes.
- `app/infra/db/database.py` no longer owns the simple registered index DDL for tables present in the registry.
- DAO ensure functions no longer hand-write simple indexes that are registered for their table.
- Regression tests prove registry-owned indexes are created through bootstrap/DAO paths and source-level checks prove the moved index SQL is no longer locally duplicated.
- Compile, focused schema tests, ruff `E9,F63,F7,F82`, `git diff --check`, and full pytest pass in one consolidated verification pass.

## Out of Scope

- Do not rewrite `db_manager.py` repair/export/import behavior in this slice.
- Do not move legacy compatibility rebuild/drop migrations from media request, gap, or dedupe DAOs.
- Do not change table shapes, index names, route responses, or public DAO function names.
- Do not split large domain files in this slice.

## Technical Approach

- Add `TABLE_INDEXES: dict[str, list[str]]` in `app/infra/db/schema_registry.py`.
- Add `apply_registered_indexes(...)` and call it from `ensure_registered_table(...)` and `ensure_playback_table(...)`.
- Update database bootstrap and affected DAOs to call the registry/bootstrap helper instead of local `CREATE INDEX` statements.
- Extend existing schema bootstrap registry tests around database init, notification, session, audit, plugin, and local playback index behavior.

## Technical Notes

- Audit reference: `docs/架构审计.md` P2 issue 4, schema fact-source split.
- Current evidence: table CREATE/ALTER statements are already mostly in `schema_registry`, but simple `CREATE INDEX IF NOT EXISTS ...` statements still exist in `app/infra/db/database.py`, `app/infra/db/audit_logger_dao.py`, `app/infra/db/session_dao.py`, `app/infra/db/notification_dao.py`, `app/domains/notifications/bot_service_dao.py`, and `app/plugins/plugin_dao.py`.
- Keep using `uv run --with-requirements requirements.txt` for Python verification.
