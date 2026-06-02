# Compat Sensitive Schema Registry Bootstrap

## Context

`docs/架构审计.md` calls out split schema facts as an active P2 architecture issue. `app.infra.db.database.init_db()` still keeps handwritten compatibility DDL for registry-owned tables that already have canonical metadata and safe ALTER entries in `app.infra.db.schema_registry`:

- `invitations`
- `sys_license`
- `tg_user_bindings`

These tables were previously left local because they are more ALTER-sensitive than simple compatibility tables. Their registry schemas and `TABLE_ALTERS` are now established by focused DAO/bootstrap tests, so the compatibility initialization path can use the same registry helper.

## Goal

Route `init_db()` compatibility creation for `invitations`, `sys_license`, and `tg_user_bindings` through `schema_bootstrap.ensure_registered_table(...)`, removing duplicate local DDL and local ALTER copies.

## Scope

- Add a small `_REGISTRY_COMPAT_SENSITIVE_INIT_TABLES` list in `app.infra.db.database`.
- Use `ensure_registered_table(c, table_name)` for `invitations`, `sys_license`, and `tg_user_bindings` in `init_db()`.
- Remove local compatibility `CREATE TABLE IF NOT EXISTS` and local ALTER statements for those three tables.
- Preserve local high-risk compatibility DDL for `media_requests` and playback-table compatibility.
- Update focused database-init tests to prove registry-backed creation and registered ALTER application in the compatibility database.
- Update backend database guidelines.

## Non-Goals

- No migration of `media_requests` or `request_users` rebuild logic.
- No changes to Pro license DAO behavior.
- No changes to invitation or user-bot DAO behavior.
- No playback table registry migration.
- No index metadata centralization.

## Acceptance Criteria

- `init_db(skip_migration=True)` creates `invitations`, `sys_license`, and `tg_user_bindings` in the compatibility database from registry metadata.
- Registered ALTER columns are present for legacy table shapes:
  - `invitations.route_mode`, `invitations.req_free`, `invitations.req_free_count`
  - `sys_license.max_devices`, `sys_license.current_devices`
  - `tg_user_bindings.tg_display_name`
- Local duplicate DDL / ALTER statements for these three tables are removed from `init_db()`.
- Existing local `media_requests` compatibility DDL remains untouched for its own high-risk slice.
- Focused checks, compile/lint checks, `git diff --check`, and full pytest pass.
