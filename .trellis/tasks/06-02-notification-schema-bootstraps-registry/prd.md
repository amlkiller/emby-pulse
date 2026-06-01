# Notification Schema Bootstraps Registry

## Goal

Continue the P2 schema fact-source cleanup from `docs/架构审计.md` by routing small notification/message bootstrap helpers through `app.infra.db.schema_registry` for registry-owned tables.

## Requirements

- Update these helpers to create registry-owned tables from `TABLE_SCHEMAS`:
  - `app.domains.notifications.bot_service_dao.ensure_request_admin_messages_table()` -> `request_admin_messages`
  - `app.domains.notifications.notify_rule_dao.ensure_bot_notify_mutes_table()` -> `bot_notify_mutes`
  - `app.domains.notifications.notify_admin_dao.ensure_notify_rules_table()` -> `notify_rules`
  - `app.domains.notifications.message_dao.ensure_msg_tables()` -> `msg_conversations`, `msg_items`, `msg_notify_block`
  - `app.domains.notifications.message_dao.ensure_mute_table()` -> `user_mutes`
- Preserve the existing `request_admin_messages` index creation.
- Preserve public DAO function names and existing read/write behavior.
- Add focused regression coverage proving the selected helpers consume registry definitions and no longer contain local duplicate registry-owned table DDL.

## Acceptance Criteria

- [x] Selected helpers import and use `TABLE_SCHEMAS` from `app.infra.db.schema_registry`.
- [x] `request_admin_messages`, `bot_notify_mutes`, `notify_rules`, `msg_conversations`, `msg_items`, `msg_notify_block`, and `user_mutes` are created from registry definitions.
- [x] `request_admin_messages` still creates `idx_request_admin_messages_tmdb`.
- [x] Selected helpers contain no local `CREATE TABLE IF NOT EXISTS` DDL for the registry-owned tables in scope.
- [x] Existing DAO read/write behavior is unchanged.
- [x] Focused notification/message schema bootstrap tests pass.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

- Import `TABLE_SCHEMAS` from `app.infra.db.schema_registry` in the selected DAO modules.
- Replace local table DDL with `conn.execute(TABLE_SCHEMAS["table_name"])` or a small loop over the scoped table names.
- Keep index DDL local for `request_admin_messages`, because it is not a table schema definition in `TABLE_SCHEMAS`.
- Use temp database tests by monkeypatching `system_store.db_path`.

## Out of Scope

- Do not modify `message_dao.ensure_announcement_tables()`; `announcements` and `announcement_reads` are not registry-owned in this slice.
- Do not change message, notification, mute, or bot notification API behavior.
- Do not add new schema fields.
- Do not modify `app/infra/db/database.py` bootstrap blocks in this slice.

## Verification Plan

- Focused tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/test_notification_schema_bootstraps_registry.py -v`.
- Schema boundary tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/test_schema_registry_boundary.py tests/test_small_schema_bootstraps_registry.py tests/test_system_repair_schema_registry.py tests/test_gap_schema_bootstrap_registry.py tests/test_dedupe_schema_bootstrap_registry.py -v`.
- Compile/import: `uv run --with-requirements requirements.txt python -m compileall app/domains/notifications/bot_service_dao.py app/domains/notifications/notify_rule_dao.py app/domains/notifications/notify_admin_dao.py app/domains/notifications/message_dao.py tests/test_notification_schema_bootstraps_registry.py`.
- Full tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v`.

## Verification Results

- Focused tests: `3 passed, 1 warning`.
- Schema registry regression batch: `23 passed, 1 warning`.
- Compile/import: passed for selected notification DAO modules and `tests/test_notification_schema_bootstraps_registry.py`.
- Ruff changed files: passed.
- Full tests: `128 passed, 3 warnings`.
- `git diff --check`: passed.
