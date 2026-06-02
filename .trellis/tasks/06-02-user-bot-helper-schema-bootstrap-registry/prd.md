# User Bot Helper Schema Registry Bootstrap

## Context

The schema registry migration has already moved the core Telegram user-bot tables (`tg_user_bindings`, `tg_user_blacklist`, and `tg_reg_logs`) into `app.infra.db.schema_registry`. `app.domains.users.user_bot_dao.ensure_user_bot_tables()` still keeps local DDL for helper tables `tg_bot_users` and `tg_channel_bindings`, which leaves the user-bot bootstrap split across registry-owned and DAO-local schema definitions.

## Goal

Move the remaining user-bot helper table definitions into the central schema registry and make `ensure_user_bot_tables()` create every user-bot table through the registry-backed bootstrap path.

## Scope

- Register `tg_bot_users` and `tg_channel_bindings` in `SYSTEM_TABLES`.
- Add canonical `TABLE_SCHEMAS` entries for both helper tables.
- Route `ensure_user_bot_tables()` through `schema_bootstrap.ensure_registered_table(...)` for all user-bot tables.
- Remove local helper-table `CREATE TABLE IF NOT EXISTS` SQL from `user_bot_dao.py`.
- Preserve existing bot user, binding, registration log, and channel binding DAO behavior.
- Update focused schema-registry tests and backend database guidelines.

## Non-Goals

- No schema changes beyond moving the existing helper-table DDL into the registry.
- No index centralization.
- No broader database-init compatibility migration for remaining high-risk local DDL.
- No router/service response or behavior changes.

## Acceptance Criteria

- `ensure_user_bot_tables()` creates `tg_user_bindings`, `tg_user_blacklist`, `tg_reg_logs`, `tg_bot_users`, and `tg_channel_bindings` from registry metadata.
- Legacy `tg_user_bindings` rows still receive registered optional columns and preserve existing row data.
- Bot user and channel binding smoke paths work after bootstrap:
  - `record_bot_user`
  - `list_bot_users`
  - `get_bot_user_name`
  - `bind_channel`
  - `get_channel_binding`
  - `unbind_channel`
- Focused tests assert no local duplicate DDL remains in `user_bot_dao.py` for any registry-owned user-bot table.
- Backend database guidelines describe the new registry-owned helper table contract.
- Focused checks, compile/lint checks, `git diff --check`, and full pytest pass.
