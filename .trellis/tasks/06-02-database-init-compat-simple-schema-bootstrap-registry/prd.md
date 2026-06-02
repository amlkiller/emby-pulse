# Refactor database init compatibility simple tables through registry

## Problem

`app.infra.db.database.init_db()` still keeps local compatibility DDL for several simple registry-owned system tables in the legacy `DB_PATH` initialization branch. These tables are already represented in `app.infra.db.schema_registry` and are created by the primary system-database initialization path, so the compatibility branch remains a duplicate schema fact source called out in `docs/架构审计.md`.

## Scope

- Route low-risk simple registry-owned compatibility tables in `init_db()` through `schema_bootstrap.ensure_registered_table(...)`.
- Cover only tables that do not require special compatibility migration decisions in this slice:
  - `tv_calendar_cache`
  - `request_users`
  - `request_admin_messages`
  - `insight_ignores`
  - `gap_records`
  - `risk_logs`
  - `tg_user_blacklist`
  - `plugin_state`
  - `sys_dashboard`
  - `tg_reg_logs`
- Preserve existing local DDL for compatibility tables with active ALTER semantics or higher-risk behavior, such as `invitations`, `sys_license`, `media_requests`, `sys_notifications`, and `tg_user_bindings`.
- Add focused regression coverage proving registry creation and source ownership for this compatibility table set.
- Update backend database guidelines with the compatibility simple-table registry contract.

## Out of Scope

- Migrating `media_requests`, `request_users` domain migrations, login/API token tables, user tags, point game tables, invitations, license, sys notifications, or Telegram bindings with ALTER compatibility semantics.
- Changing database path behavior or startup order.
- Broad lint cleanup of `app.infra.db.database`.

## Acceptance

- `init_db()` creates the selected compatibility simple tables through registry bootstrap instead of local DDL.
- Fresh temporary compatibility database initialization still creates the selected tables.
- Local DDL remains for explicitly out-of-scope high-risk or ALTER-sensitive tables.
- Focused database-init/schema registry tests, compile/import checks, and the full pytest suite pass.
