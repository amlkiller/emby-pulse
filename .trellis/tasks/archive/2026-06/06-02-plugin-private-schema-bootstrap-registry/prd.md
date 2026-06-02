# Plugin private schema registry bootstrap

## Goal

Continue the P2 schema fact-source cleanup from `docs/架构审计.md` by moving low-risk plugin-private DAO table definitions into `app.infra.db.schema_registry` and routing their bootstrap helpers through `schema_bootstrap.ensure_registered_table(...)`.

## Requirements

- Register these plugin-private tables in `SYSTEM_TABLES` and `TABLE_SCHEMAS`:
  - `temp_accounts`
  - `temp_account_password_history`
  - `season_poster_logs`
  - `season_poster_cache`
  - `emby_restart_history`
  - `smart_collections`
  - `smart_collection_items`
  - `smart_collection_sync_logs`
- Move compatible optional-column upgrades for `temp_accounts` into `TABLE_ALTERS`.
- Route the following helpers through `ensure_registered_table(...)`:
  - `app.plugins.temp_account.temp_account_dao.ensure_temp_account_tables()`
  - `app.plugins.season_poster_updater.season_poster_dao.ensure_season_poster_tables()`
  - `app.plugins.emby_restart.emby_restart_dao.ensure_emby_restart_history_table()`
  - `app.plugins.smart_collections.smart_collection_dao.ensure_smart_collection_tables()`
- Preserve existing DAO read/write behavior and idempotency.
- Keep unrelated plugin tables that are already registered (`plugin_state`, `plugin_logs`, `keep_alive_violations`) unchanged except for test context if needed.
- Keep non-plugin local DDL such as `user_tags`, `tv_series_status`, `media_requests`, compatibility invitations/license/TG bindings, playback compatibility DDL, and session/audit helper tables out of scope.
- Add focused regression coverage proving registry-backed creation, registered temp-account ALTER application, plugin DAO smoke paths, and no local duplicate DDL/ALTER for newly registry-owned tables.
- Update backend database guidelines with the plugin-private registry contract.

## Acceptance Criteria

- [ ] All listed plugin-private tables are present in `SYSTEM_TABLES` and `TABLE_SCHEMAS`.
- [ ] `TABLE_ALTERS["temp_accounts"]` contains compatible optional columns currently added locally.
- [ ] The four plugin helper functions listed above contain no local `CREATE TABLE IF NOT EXISTS` DDL for newly registry-owned tables.
- [ ] `ensure_temp_account_tables()` contains no local `ALTER TABLE temp_accounts ADD COLUMN` statements.
- [ ] Fresh temporary system DB bootstrap creates registered columns for all listed tables.
- [ ] Legacy `temp_accounts` table shapes upgrade through registered ALTERs.
- [ ] Selected temp-account, season-poster, emby-restart, and smart-collection DAO smoke paths work after registry bootstrap.
- [ ] Focused plugin-private schema tests, compile/import checks, ruff checks for changed files, `git diff --check`, and the full pytest suite pass.

## Definition of Done

- Tests added or updated for changed behavior.
- Changed Python files compile through `uv run --with-requirements requirements.txt`.
- Ruff critical checks pass for changed Python files.
- Full pytest suite passes.
- Work is committed as one coherent plugin-private schema-registry slice, then the task is archived and journaled.

## Technical Approach

Add schema definitions matching the current local DDL and replace each helper's local DDL with a small loop over registry-owned table names. Keep DAO data manipulation, plugin log clearing, user metadata updates, and plugin runtime behavior unchanged. Apply `temp_accounts` optional-column compatibility through `TABLE_ALTERS`.

## Out of Scope

- Changing plugin runtime behavior, scheduler lifecycle, plugin config payloads, or route responses.
- Registering unrelated non-plugin compatibility tables.
- Refactoring plugin services beyond schema bootstrap helpers.
- Centralizing index metadata.

## Technical Notes

- `docs/架构审计.md` P2 identifies plugin DAO DDL as part of the schema fact-source split.
- Existing low-risk DAO helpers are simple `CREATE TABLE IF NOT EXISTS` bootstraps with smokeable read/write paths.
- `temp_accounts` currently has local optional-column ALTERs for route/tag/request-permission fields; those are compatible with `schema_bootstrap.ensure_registered_table(...)`.
