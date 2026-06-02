# Gap Schema Bootstrap Convergence

## Goal

Move `app/domains/media_requests/gap_dao.py` off local schema-registry execution logic and onto the shared `app.infra.db.schema_bootstrap.ensure_registered_table()` helper, reducing the schema fact-source split identified in `docs/架构审计.md`.

## Requirements

- Replace direct `TABLE_SCHEMAS` / `TABLE_ALTERS` usage in `gap_dao.ensure_gap_tables()` with `ensure_registered_table()`.
- Remove local duplicate-column ALTER handling and the DAO's `sqlite3` dependency.
- Preserve idempotent initialization of `gap_config`, `gap_records`, `gap_perfect_series`, and `gap_scan_cache`.
- Preserve registered `gap_perfect_series.tmdb_id` ALTER application for legacy tables.
- Preserve default `gap_config.cache_interval_hours = 6` insertion.
- Preserve legacy `gap_scan_cache` rebuild from old `series_id` shape to registry `result_json` shape.
- Keep all gap DAO query/write behavior unchanged.
- Update focused schema tests to assert the DAO uses the shared schema bootstrap helper and no local DDL/ALTER execution.

## Acceptance Criteria

- [ ] `ensure_gap_tables()` still creates all gap registry tables.
- [ ] Registered `gap_perfect_series` alters still apply to a legacy table.
- [ ] Existing legacy `gap_scan_cache` migration still rebuilds to registry shape.
- [ ] `gap_dao.py` imports `ensure_registered_table` and does not import `TABLE_SCHEMAS` / `TABLE_ALTERS`.
- [ ] Focused gap schema tests pass.
- [ ] Full `uv run pytest tests/ -v` passes before committing.

## Definition of Done

- Behavior-preserving schema bootstrap refactor only.
- Verification commands use `uv run`.
- Spec updates are made only if this task changes durable schema-bootstrap conventions.
- Work commit is created before Trellis archive and journal commits.

## Out of Scope

- Gap scan algorithm changes.
- Gap route/API response changes.
- Media request facade or wrapper cleanup.
- Broad schema registry redesign.

## Technical Notes

- Audit source: `docs/架构审计.md` P2 issue 4, schema fact-source split.
- Target file: `app/domains/media_requests/gap_dao.py`.
- Existing focused tests: `tests/test_gap_schema_bootstrap_registry.py`.
- Shared helper: `app/infra/db/schema_bootstrap.py::ensure_registered_table`.
- Legacy `gap_scan_cache` rebuild remains a local data-shape migration decision, but the recreated table should come from the shared bootstrap helper.
