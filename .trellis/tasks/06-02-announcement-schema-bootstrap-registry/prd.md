# Refactor announcement schema bootstrap through registry

## Problem

`app.domains.notifications.message_dao.ensure_announcement_tables()` still owns local DDL for `announcements` and `announcement_reads`. These notification tables are part of the system database, but their schema is not represented in `app.infra.db.schema_registry`, extending the schema fact-source split called out in `docs/架构审计.md`.

## Scope

- Register `announcements` and `announcement_reads` in `app.infra.db.schema_registry`.
- Route `message_dao.ensure_announcement_tables()` through registry-backed table creation.
- Preserve existing announcement CRUD, active announcement listing, read tracking, and view-count behavior.
- Add focused regression coverage proving registry ownership and DAO smoke paths.
- Update backend database guidelines with the announcement registry contract.

## Out of Scope

- Changing announcement route behavior, payload shape, ordering, or permissions.
- Migrating unrelated message tables beyond existing registry-backed behavior.
- Migrating notification delivery, bot notification, or user mute logic.
- Broad lint cleanup of `message_dao.py`.

## Acceptance

- `announcements` and `announcement_reads` exist in `SYSTEM_TABLES` and `TABLE_SCHEMAS`.
- `ensure_announcement_tables()` creates both tables from registry metadata instead of local DDL.
- Fresh temporary system database bootstrap supports announcement create/list/update/view/read DAO paths.
- Focused notification schema tests, compile/import checks, and the full pytest suite pass.
