# Auth and API token schema registry bootstrap

## Goal

Continue the P2 schema fact-source cleanup from `docs/架构审计.md` by moving `login_failures` and `api_tokens` table definitions into `app.infra.db.schema_registry` and routing `app.infra.db.database._create_system_tables()` through `schema_bootstrap.ensure_registered_table(...)` for those registry-owned tables.

## Requirements

- Register `login_failures` and `api_tokens` in `SYSTEM_TABLES` and `TABLE_SCHEMAS`.
- Route their table creation in `_create_system_tables()` through `ensure_registered_table(...)`.
- Preserve existing index creation for login failure lookup and API token lookup.
- Preserve auth/login-lock DAO behavior and API token store behavior.
- Keep unrelated local DDL such as `user_tags`, `tv_series_status`, `media_requests`, point game tables, invitations, license, and Telegram binding compatibility DDL out of this task.
- Add focused regression coverage proving registry-backed creation, preserved indexes, auth/API token smoke paths, and no local duplicate DDL for these two tables.
- Update backend database guidelines with the auth/API token system table registry contract.

## Acceptance Criteria

- [ ] `login_failures` and `api_tokens` are present in `SYSTEM_TABLES` and `TABLE_SCHEMAS`.
- [ ] `_create_system_tables()` contains no local `CREATE TABLE IF NOT EXISTS login_failures` or `CREATE TABLE IF NOT EXISTS api_tokens` DDL.
- [ ] Fresh temporary system DB initialization creates both tables with registered columns and preserved indexes.
- [ ] Auth login failure DAO smoke paths work after registry bootstrap.
- [ ] API token store smoke paths work after registry bootstrap.
- [ ] Focused database-init/schema registry tests, compile/import checks, ruff checks for changed files, `git diff --check`, and full pytest suite pass.

## Definition of Done

- Tests added or updated for changed behavior.
- Changed Python files compile through `uv run --with-requirements requirements.txt`.
- Ruff critical checks pass for changed Python files.
- Full pytest suite passes.
- Work is committed as one coherent schema-registry slice, then the task is archived and journaled.

## Technical Approach

Add registry definitions matching the current local DDL, include the two tables in `_REGISTRY_SYSTEM_INIT_TABLES`, and replace the local CREATE statements in `_create_system_tables()` with `ensure_registered_table(...)`. Keep indexes local because index ownership is not yet centralized in the schema registry.

## Out of Scope

- Registering or migrating `user_tags`, `tv_series_status`, `media_requests`, point game tables, invitations, sys license, Telegram bindings, or playback compatibility DDL.
- Changing login lock behavior, API token JWT behavior, route payloads, or token hashing.
- Centralizing index metadata in the registry.

## Technical Notes

- `docs/架构审计.md` P2 identifies schema fact-source split as a current cleanup area.
- Current local duplicates were found in `app.infra.db.database._create_system_tables()`.
- `app.domains.users.auth_dao` reads/writes `login_failures`.
- `app.infra.db.api_token_store` reads/writes `api_tokens`, while `app.domains.system.api_token_dao` remains a compatibility wrapper.
