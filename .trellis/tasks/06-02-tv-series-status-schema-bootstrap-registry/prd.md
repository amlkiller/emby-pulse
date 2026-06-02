# TV Series Status Schema Registry Bootstrap

## Context

`docs/架构审计.md` identifies split schema facts as an active P2 architecture issue. `tv_series_status` is still created by handwritten DDL in `app.infra.db.database._create_system_tables()`, while the read/write behavior lives in `app.domains.playback.calendar_dao`. This keeps another low-risk startup table outside `app.infra.db.schema_registry`.

## Goal

Make `tv_series_status` a registry-owned system table and route system database startup creation through `schema_bootstrap.ensure_registered_table(...)`.

## Scope

- Add `tv_series_status` to `SYSTEM_TABLES`.
- Add a canonical `TABLE_SCHEMAS["tv_series_status"]` entry matching the existing table shape.
- Add `tv_series_status` to `_REGISTRY_SYSTEM_INIT_TABLES` in `app.infra.db.database`.
- Remove local `CREATE TABLE IF NOT EXISTS tv_series_status` from `_create_system_tables()`.
- Add focused tests proving registry ownership, startup creation, calendar DAO smoke behavior, and no local duplicate DDL.
- Update backend database guidelines with the new `tv_series_status` registry contract.

## Non-Goals

- No changes to calendar service polling or cache replacement behavior.
- No changes to `tv_calendar_cache` schema or logic.
- No high-risk migration for `media_requests` / `request_users`.
- No index metadata centralization.
- No cross-domain facade work.

## Acceptance Criteria

- `init_system_db()` creates `tv_series_status` from registry metadata.
- `tv_series_status` exists in both `SYSTEM_TABLES` and `TABLE_SCHEMAS`.
- The table keeps the existing columns: `tmdb_id`, `series_name`, `status`, `last_checked`, and `updated_at`.
- Calendar DAO smoke paths work after registry-backed system initialization:
  - `save_series_status`
  - `list_ended_series_tmdb_ids`
- `app.infra.db.database._create_system_tables()` has no local `CREATE TABLE IF NOT EXISTS tv_series_status` DDL.
- Focused checks, compile/lint checks, `git diff --check`, and full pytest pass.
