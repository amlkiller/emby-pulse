# Dashboard Layout Schema Bootstrap Convergence

## Goal

Move the `sys_dashboard` table bootstrap in `app/domains/system/system_tool_dao.py` dashboard layout helpers onto the shared `app.infra.db.schema_bootstrap.ensure_registered_table()` helper, reducing the schema fact-source split identified in `docs/架构审计.md`.

## Requirements

- Replace direct `TABLE_SCHEMAS["sys_dashboard"]` execution in `get_dashboard_layout()` and `save_dashboard_layout()` with `ensure_registered_table()`.
- Preserve `repair_core_system_tables()` behavior and its registry-metadata repair/upgrade message semantics.
- Preserve dashboard layout read/write behavior and JSON serialization.
- Keep `sys_dashboard` schema metadata owned by `schema_registry`.
- Update focused schema tests to assert dashboard helpers use the shared schema bootstrap helper and no local dashboard DDL remains.

## Acceptance Criteria

- [ ] `get_dashboard_layout()` still returns `None` before a layout is saved.
- [ ] `save_dashboard_layout()` still creates `sys_dashboard` and preserves layout JSON.
- [ ] `system_tool_dao.py` uses `ensure_registered_table(cursor, "sys_dashboard")` for dashboard helpers.
- [ ] `repair_core_system_tables()` tests still pass.
- [ ] Focused small schema bootstrap tests pass.
- [ ] Full `uv run pytest tests/ -v` passes before committing.

## Definition of Done

- Behavior-preserving schema bootstrap refactor only.
- Verification commands use `uv run`.
- Spec updates are made only if this task changes durable schema-bootstrap conventions.
- Work commit is created before Trellis archive and journal commits.

## Out of Scope

- Repair helper redesign.
- Dashboard layout payload or UI changes.
- Wrapper/pass-through cleanup.
- Broad schema registry redesign.

## Technical Notes

- Audit source: `docs/架构审计.md` P2 issue 4, schema fact-source split.
- Target file: `app/domains/system/system_tool_dao.py`.
- Existing focused tests: `tests/test_small_schema_bootstraps_registry.py` and `tests/test_system_repair_schema_registry.py`.
- Shared helper: `app/infra/db/schema_bootstrap.py::ensure_registered_table`.
