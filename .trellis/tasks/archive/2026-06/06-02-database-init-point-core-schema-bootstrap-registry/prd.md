# Refactor database init point core schema bootstrap through registry

## Problem

`app.infra.db.database.init_db()` still keeps local startup DDL for registry-owned `point_logs` and `point_config` in its compatibility initialization path. The point DAO now creates these tables through `app.infra.db.schema_bootstrap.ensure_registered_table(...)`, so the database initializer remains a duplicate schema fact source for the same tables.

## Scope

- Route `point_logs` and `point_config` startup creation in `app.infra.db.database` through `schema_bootstrap.ensure_registered_table(...)`.
- Keep existing point default config insertion behavior owned by `app.domains.points.point_dao.ensure_points_schema()`.
- Preserve local initialization for unregistered or high-risk startup tables.
- Add focused regression coverage proving database init no longer keeps local point core DDL and still creates the tables on a fresh database.
- Update backend database guidelines with the database-init point-core registry contract.

## Out of Scope

- Registering point game tables such as lottery, scratch cards, red packets, transfer, robbery, or PK tables.
- Migrating `media_requests`, `request_users`, login/API token tables, user tags, or announcement tables.
- Broad lint cleanup of `app.infra.db.database`.

## Acceptance

- `app.infra.db.database` routes startup creation of `point_logs` and `point_config` through registry bootstrap instead of local DDL.
- Fresh system database initialization still creates `point_logs` and `point_config`.
- Existing database-init registry tests cover the new startup table set and source boundary.
- Focused tests, compile/import checks, and the full pytest suite pass.
