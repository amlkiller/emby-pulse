# Refactor PWA schema bootstrap through registry

## Problem

`app.domains.pwa.pwa_dao` still owns local `CREATE TABLE IF NOT EXISTS` statements for `pwa_config` and `user_pwa_icons`. This keeps PWA table definitions outside the centralized schema registry and extends the schema fact-source split called out in `docs/架构审计.md`.

## Scope

- Register `pwa_config` and `user_pwa_icons` in `app.infra.db.schema_registry`.
- Change PWA DAO bootstrap helpers to create registry-owned tables through `app.infra.db.schema_bootstrap.ensure_registered_table`.
- Preserve existing PWA config and per-user icon read/write behavior.
- Add focused regression coverage proving registry ownership and DAO smoke paths.
- Update backend database guidelines with the PWA registry contract.

## Out of Scope

- PWA route behavior changes.
- Plugin table migration.
- Broad database migration rewrites outside the PWA bootstrap path.

## Acceptance

- `pwa_config` and `user_pwa_icons` exist in `SYSTEM_TABLES` and `TABLE_SCHEMAS`.
- PWA bootstrap helpers no longer contain local PWA `CREATE TABLE` DDL.
- PWA config and user-icon DAO paths work against a fresh temporary system database.
- Focused schema boundary tests and the full pytest suite pass.
