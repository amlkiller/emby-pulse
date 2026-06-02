# Plugin DAO schema registry bootstrap batch

## Goal

Continue the P2 schema fact-source cleanup from `docs/架构审计.md` by routing registry-owned plugin and plugin-adjacent DAO bootstrap tables through `app.infra.db.schema_bootstrap.ensure_registered_table(...)` instead of keeping duplicate local DDL/ALTER statements in plugin DAOs.

## Requirements

- `app.plugins.plugin_dao.ensure_plugin_tables()` must create registry-owned `plugin_state` and `plugin_logs` through `ensure_registered_table(...)`.
- `app.plugins.plugin_dao.ensure_plugin_tables()` must keep the existing `idx_plugin_logs_plugin_id` index creation behavior.
- `app.plugins.keep_alive.keep_alive_dao.ensure_keep_alive_violations_table()` must create and upgrade `keep_alive_violations` through `ensure_registered_table(...)`.
- Existing plugin state/config/log DAO behavior and keep-alive violation DAO behavior must remain unchanged.
- Add focused regression coverage proving registry-backed creation, registered keep-alive ALTER application, preserved DAO smoke paths, and no local duplicate DDL/ALTER for these registry-owned tables.
- Update backend database guidelines with the plugin DAO bootstrap registry contract.

## Acceptance Criteria

- [ ] `plugin_dao.ensure_plugin_tables()` contains no local `CREATE TABLE IF NOT EXISTS plugin_state` or `CREATE TABLE IF NOT EXISTS plugin_logs` DDL.
- [ ] `keep_alive_dao.ensure_keep_alive_violations_table()` contains no local `CREATE TABLE IF NOT EXISTS keep_alive_violations` DDL or local `ALTER TABLE keep_alive_violations ADD COLUMN ...` statements.
- [ ] Fresh temporary system database bootstrap creates `plugin_state`, `plugin_logs`, and `keep_alive_violations` with columns from the registry.
- [ ] Legacy `keep_alive_violations` shapes receive registered `action` and `disabled` columns through `TABLE_ALTERS`.
- [ ] Plugin DAO and keep-alive DAO smoke paths still work after registry bootstrap.
- [ ] Focused schema-registry tests, compile/import checks, ruff checks for changed files, `git diff --check`, and full pytest suite pass.

## Definition of Done

- Tests added or updated for changed behavior.
- Changed Python files compile through `uv run --with-requirements requirements.txt`.
- Ruff critical checks pass for changed Python files.
- Full pytest suite passes.
- Work is committed as one coherent batch, then the task is archived and journaled.

## Technical Approach

Use the existing `schema_bootstrap.ensure_registered_table(cursor, table_name)` helper inside the plugin DAOs. Keep non-table extras, such as `idx_plugin_logs_plugin_id`, local to the DAO because the registry currently owns table schemas and safe ALTERs, not DAO-specific indexes.

## Out of Scope

- Registering plugin-private business tables such as temp-account, smart-collection, season-poster, WebDAV, or Emby restart plugin tables.
- Changing plugin enable/disable scheduler behavior.
- Changing keep-alive plugin policy, route payloads, or violation semantics.
- Migrating complex media request, invitation, playback, or point game tables.

## Technical Notes

- `docs/架构审计.md` P2 calls out split schema fact sources across infra, domain, and plugin DAOs.
- `app.infra.db.schema_registry` already owns `plugin_state`, `plugin_logs`, and `keep_alive_violations`.
- `TABLE_ALTERS["keep_alive_violations"]` already owns the `action` and `disabled` optional-column migration.
- Current local duplicates were found in `app/plugins/plugin_dao.py` and `app/plugins/keep_alive/keep_alive_dao.py`.
