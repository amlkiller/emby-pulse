# Refactor point core schema bootstrap through registry

## Problem

`app.domains.points.point_dao.ensure_points_schema()` still keeps local DDL for `point_logs` and `point_config`, even though both tables are already owned by `app.infra.db.schema_registry`. This extends the schema fact-source split called out in `docs/架构审计.md`.

## Scope

- Route `point_logs` and `point_config` creation through `schema_bootstrap.ensure_registered_table(...)`.
- Preserve `users_meta.points` bootstrap, point default config insertion, and existing point DAO read/write behavior.
- Leave unregistered point game tables local for a later explicit migration slice.
- Add focused regression coverage for registry-backed point core bootstrap.
- Update backend database guidelines with the point core registry contract.

## Out of Scope

- Registering lottery, red packet, transfer, robbery, scratch-card, or PK tables.
- Changing point route behavior or point economy defaults.
- Broad lint cleanup of `point_dao.py`.

## Acceptance

- `ensure_points_schema()` uses registry bootstrap for `point_logs` and `point_config`.
- Local point DAO DDL remains only for unregistered point game tables.
- A fresh temporary system database can bootstrap points schema, insert defaults, and use selected DAO paths.
- Focused tests, compile/import checks, and the full pytest suite pass.
