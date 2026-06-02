# Refactor database init message tables through registry

## Problem

`app.infra.db.database.init_db()` still keeps a late compatibility block that locally creates `msg_conversations`, `msg_items`, and `msg_notify_block` in the system database. These tables are already owned by `app.infra.db.schema_registry` and are also created by the main `_REGISTRY_SYSTEM_INIT_TABLES` path, so this block remains a duplicate schema fact source called out by `docs/架构审计.md`.

## Scope

- Route the late `init_db()` message-table compatibility block through `schema_bootstrap.ensure_registered_table(...)`.
- Preserve existing behavior that ensures message tables exist in `SYSTEM_DB_PATH` after `init_db(skip_migration=True)`.
- Leave unrelated compatibility DDL in `init_db()` and `_create_system_tables()` unchanged.
- Add focused regression coverage proving the compatibility block no longer keeps local message table DDL.
- Update backend database guidelines with the database-init message table registry contract.

## Out of Scope

- Changing message center DAO behavior, route payloads, or unread-count semantics.
- Migrating media request, login/API token, invitation, user-tag, or point game table DDL.
- Broad lint cleanup of `app.infra.db.database`.

## Acceptance

- `init_db()` creates late compatibility message tables through registry bootstrap instead of local DDL.
- Fresh temporary system database initialization still creates `msg_conversations`, `msg_items`, and `msg_notify_block`.
- Focused database-init/schema registry tests cover source ownership and behavior.
- Focused tests, compile/import checks, and the full pytest suite pass.
