# Refactor database init sys notifications through registry

## Problem

`app.infra.db.database.init_db()` still keeps local compatibility DDL for registry-owned `sys_notifications`. The primary system database initialization already creates this table through `app.infra.db.schema_bootstrap.ensure_registered_table(...)` and applies `TABLE_ALTERS["sys_notifications"]`, so the legacy compatibility branch remains a duplicate schema fact source.

## Scope

- Route `sys_notifications` creation in the `init_db()` compatibility branch through `schema_bootstrap.ensure_registered_table(...)`.
- Preserve registered ALTER behavior such as `sys_notifications.is_cleared`.
- Keep local DDL for unrelated high-risk compatibility tables such as `invitations`, `sys_license`, `media_requests`, and `tg_user_bindings`.
- Add focused regression coverage proving compatibility initialization uses registry metadata for `sys_notifications`.
- Update backend database guidelines with the `sys_notifications` compatibility bootstrap contract.

## Out of Scope

- Migrating invitations, license, media request, Telegram binding, login/API token, user tag, or point game table compatibility DDL.
- Changing notification DAO behavior or system notification payloads.
- Broad lint cleanup of `app.infra.db.database`.

## Acceptance

- `init_db()` creates compatibility `sys_notifications` through registry bootstrap instead of local DDL.
- A fresh temporary compatibility database contains `sys_notifications` with registered columns after `init_db(skip_migration=True)`.
- Focused database-init/schema registry tests, compile/import checks, and the full pytest suite pass.
