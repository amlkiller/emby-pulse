# Refactor Pro License Schema Bootstrap Through Registry

## Goal

Reduce schema fact-source drift called out in `docs/架构审计.md` by routing the registry-owned `sys_license` bootstrap in `app.domains.system.pro_license_dao` through `app.infra.db.schema_registry`.

## Requirements

* `pro_license_dao.ensure_pro_schema()` must create `sys_license` from `TABLE_SCHEMAS["sys_license"]`.
* Extension columns created by the DAO today, including `max_devices` and `current_devices`, must be represented by the registry and safely applied through `TABLE_ALTERS["sys_license"]`.
* Existing `replace_license()` and `get_license_status()` behavior must not change.
* The batch must include focused regression tests for registry-backed creation, legacy column migration, DAO smoke behavior, and source guards against duplicate local `sys_license` DDL.

## Acceptance Criteria

* [x] `pro_license_dao.ensure_pro_schema()` creates `sys_license` from `TABLE_SCHEMAS`.
* [x] `TABLE_SCHEMAS["sys_license"]` includes all active license columns currently created by the DAO.
* [x] `TABLE_ALTERS["sys_license"]` migrates legacy tables missing optional license columns.
* [x] Focused tests prove fresh creation, registered ALTER application, DAO behavior, and source ownership.
* [x] Schema-registry regression tests and full pytest suite pass before commit.

## Definition of Done

* Tests added or updated for changed behavior.
* Changed Python files compile.
* Ruff passes for changed Python files.
* `git diff --check` passes.
* Full pytest suite passes.
* Work is committed as one coherent schema-registry slice.

## Technical Approach

Use the same pattern as recent user-bot and auth local-users schema bootstrap refactors: import `TABLE_SCHEMAS` and `TABLE_ALTERS` in the DAO, execute registry-owned table DDL through those objects, and tolerate duplicate-column errors when replaying registered ALTER statements.

## Decision (ADR-lite)

Context: `sys_license` is already a registry-owned system table, but `pro_license_dao.ensure_pro_schema()` still keeps a local `CREATE TABLE` copy and local ALTER list, including device-count columns that are not represented by the registry.

Decision: Move `sys_license` table creation and safe optional-column migrations to `schema_registry`; keep license read/write behavior unchanged.

Consequences: Pro-license schema creation, repair, and DAO bootstrap use the same schema metadata. Future license fields should be added in the registry first, with focused migration tests.

## Out of Scope

* Changing license validation, activation, or response payload behavior.
* Rewriting `app.infra.db.database._create_system_tables()`.
* Adding new license features.

## Technical Notes

* `docs/架构审计.md` P2 identifies schema fact-source split as the current cleanup area.
* `.trellis/spec/backend/database-guidelines.md` requires registry-owned small bootstrap helpers to use `TABLE_SCHEMAS` / `TABLE_ALTERS`.
* `pro_license_dao` currently creates `max_devices` and `current_devices`; those columns must be represented by registry metadata before the local ALTER list can be removed.
