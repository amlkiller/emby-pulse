# Refactor User Meta Schema Bootstrap Through Registry

## Problem

`docs/架构审计.md` identifies split schema fact sources as an active P2 architecture risk. `users_meta` is already registry-owned, but parts of its bootstrap and column upgrade behavior still live in `app/domains/users/user_dao.py` as local ALTER logic. This can drift from `app/infra/db/schema_registry.py`, system repair, and database initialization.

## Scope

- Move safe `users_meta` optional-column upgrade metadata into `TABLE_ALTERS["users_meta"]`.
- Make `user_dao` bootstrap paths use `TABLE_SCHEMAS["users_meta"]` / `TABLE_ALTERS["users_meta"]` for registry-owned table creation and safe ALTER application.
- Preserve existing user metadata behavior and row shapes.
- Add focused regression tests proving registry-backed bootstrap and no local duplicate registry-owned DDL/ALTER remains in `user_dao`.

## Non-Goals

- Do not change `media_requests` rebuild migrations.
- Do not migrate plugin DAO database access.
- Do not redesign `users_meta` shape or alter user-facing route responses.
- Do not add unsafe generic SQLite ALTERs such as `UNIQUE`, `NOT NULL` without a safe default, or non-constant defaults.

## Acceptance Criteria

- [x] `users_meta` bootstrap in `user_dao` creates the registry-owned table from `TABLE_SCHEMAS`.
- [x] Safe optional `users_meta` columns currently added locally by `user_dao` are represented in `TABLE_ALTERS["users_meta"]`.
- [x] `user_dao` does not keep local duplicate `CREATE TABLE IF NOT EXISTS users_meta` or registry-owned `ALTER TABLE users_meta ADD COLUMN ...` SQL.
- [x] Existing DAO paths for admin-disabled, folder permissions, request permissions, tags, and route/point metadata still work after registry bootstrap.
- [x] Focused tests cover legacy minimal `users_meta` upgrade and source-boundary checks.
- [x] Full pytest suite passes, plus compile/import checks for changed Python files.
