# Refactor Auth Local Users Schema Bootstrap Through Registry

## Goal

Reduce schema fact-source drift called out in `docs/架构审计.md` by routing the registry-owned `local_users` bootstrap in `app.domains.users.auth_dao` through `app.infra.db.schema_registry`.

## Requirements

* `auth_dao.ensure_local_users_table()` must create `local_users` from `TABLE_SCHEMAS["local_users"]`.
* Active TOTP columns `totp_secret`, `totp_enabled`, and `totp_pending_secret` must be represented by the registry and applied to legacy table shapes through `TABLE_ALTERS["local_users"]`.
* Registered `local_users` ALTERs must not blindly include unsafe `UNIQUE NOT NULL` additions for columns that cannot be safely added to arbitrary legacy SQLite tables.
* Existing auth DAO behavior and query payloads must not change.
* The batch must include focused regression tests for registry-backed creation, safe legacy column migration, TOTP DAO smoke paths, and source guards against duplicate local `local_users` DDL.

## Acceptance Criteria

* [x] `auth_dao.ensure_local_users_table()` creates `local_users` from `TABLE_SCHEMAS`.
* [x] `TABLE_SCHEMAS["local_users"]` includes the active TOTP columns used by runtime auth code.
* [x] `TABLE_ALTERS["local_users"]` safely migrates optional legacy columns, including TOTP fields.
* [x] Focused tests prove fresh creation, legacy optional-column ALTER application, TOTP DAO paths, and source ownership.
* [x] Schema-registry regression tests and full pytest suite pass before commit.

## Definition of Done

* Tests added or updated for changed behavior.
* Changed Python files compile.
* Ruff passes for changed Python files.
* `git diff --check` passes.
* Full pytest suite passes.
* Work is committed as one coherent schema-registry slice.

## Technical Approach

Use the same pattern as the recent user-bot schema bootstrap refactor: import `TABLE_SCHEMAS` and `TABLE_ALTERS` in the DAO, execute registry-owned table DDL through those objects, and tolerate duplicate-column errors when replaying registered ALTER statements. Keep unsafe legacy local-user migrations out of `TABLE_ALTERS` unless they are safe SQLite `ADD COLUMN` operations.

## Decision (ADR-lite)

Context: `local_users` is already a registry-owned system table, but `auth_dao.ensure_local_users_table()` still keeps a local `CREATE TABLE` copy and a local migration map that includes active TOTP fields missing from the registry.

Decision: Move `local_users` table creation and safe optional-column migrations to `schema_registry`; keep the DAO bootstrap as a thin registry executor.

Consequences: Auth local-user schema creation, repair, and DAO bootstrap use the same schema metadata. Unsafe legacy migrations that SQLite cannot reliably apply to arbitrary existing tables are not promoted into the registry in this slice.

## Out of Scope

* Changing login, password, role, permission, or TOTP auth behavior.
* Rebuilding malformed `local_users` tables.
* Refactoring auth routes or session handling.
* Rewriting `app.infra.db.database._create_system_tables()`.

## Technical Notes

* `docs/架构审计.md` P2 identifies schema fact-source split as the current cleanup area.
* `.trellis/spec/backend/database-guidelines.md` requires registry-owned small bootstrap helpers to use `TABLE_SCHEMAS` / `TABLE_ALTERS`.
* Runtime auth code reads and writes `totp_secret`, `totp_enabled`, and `totp_pending_secret`, so those columns must be owned by the registry.
