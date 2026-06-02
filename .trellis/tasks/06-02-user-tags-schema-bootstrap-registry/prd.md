# User Tags Schema Registry Bootstrap

## Context

`docs/架构审计.md` calls out schema fact-source drift as an active P2 architecture issue. Most low-risk system tables have been moved into `app.infra.db.schema_registry`, but `user_tags` is still created by handwritten DDL inside `app.infra.db.database._create_system_tables()`. The table is used by user-management DAO/router code and temp-account tag helpers, so keeping its schema local leaves another startup-only schema definition outside the registry.

## Goal

Make `user_tags` a registry-owned system table and route system database startup creation through `schema_bootstrap.ensure_registered_table(...)`.

## Scope

- Add `user_tags` to `SYSTEM_TABLES`.
- Add a canonical `TABLE_SCHEMAS["user_tags"]` entry matching the existing table shape.
- Add `user_tags` to `_REGISTRY_SYSTEM_INIT_TABLES` in `app.infra.db.database`.
- Remove local `CREATE TABLE IF NOT EXISTS user_tags` from `_create_system_tables()`.
- Add focused tests proving registry ownership, startup creation, existing user-tag DAO behavior, and no local duplicate DDL.
- Update backend database guidelines with the new user-tags registry contract.

## Non-Goals

- No behavior changes to user tag routes or response payloads.
- No change to tag storage on `users_meta.tags`.
- No plugin API/facade refactor.
- No migration of high-risk tables such as `media_requests`, `request_users`, or `tv_series_status`.
- No index metadata centralization.

## Acceptance Criteria

- `init_system_db()` creates `user_tags` from registry metadata.
- `user_tags` exists in both `SYSTEM_TABLES` and `TABLE_SCHEMAS`.
- The table keeps the existing columns: `id`, `name`, `color`, and `created_at`.
- User tag DAO smoke paths work after registry-backed system initialization:
  - `create_user_tag`
  - `list_user_tags`
  - `save_user_tags`
  - `get_user_tags`
  - `delete_user_tag_by_name`
- `app.infra.db.database._create_system_tables()` has no local `CREATE TABLE IF NOT EXISTS user_tags` DDL.
- Focused checks, compile/lint checks, `git diff --check`, and full pytest pass.
