# Dedupe Schema Bootstrap Convergence

## Goal

Move `app/domains/playback/dedupe_dao.py` off local schema-registry execution logic and onto the shared `app.infra.db.schema_bootstrap.ensure_registered_table()` helper, reducing the schema fact-source split identified in `docs/架构审计.md`.

## Requirements

- Replace direct `TABLE_SCHEMAS` / `TABLE_ALTERS` usage in `dedupe_dao.py` with `ensure_registered_table()`.
- Remove the local `_apply_table_alters()` helper.
- Preserve the legacy `dedupe_whitelist` migration from `id/item_id/item_name` to `group_key/title/created_at`.
- Preserve idempotent initialization of `dedupe_whitelist`, `dedupe_results`, and `dedupe_config`.
- Keep Dedupe DAO query/write behavior unchanged.
- Update focused schema tests to assert the DAO uses the shared schema bootstrap helper and no local DDL/alter execution.

## Acceptance Criteria

- [ ] `init_dedupe_tables()` still creates all dedupe registry tables.
- [ ] Registered alters still apply to legacy `dedupe_results`.
- [ ] Existing legacy whitelist migration still preserves valid rows.
- [ ] `dedupe_dao.py` imports `ensure_registered_table` and does not import `TABLE_SCHEMAS` / `TABLE_ALTERS`.
- [ ] Focused dedupe schema tests pass.
- [ ] Full `uv run pytest tests/ -v` passes before committing.

## Definition of Done

- Behavior-preserving schema bootstrap refactor only.
- Verification commands use `uv run`.
- Spec updates are only made if new durable conventions are discovered beyond the existing schema-registry contract.
- Work commit is created before Trellis archive and journal commits.

## Out of Scope

- Wrapper/pass-through cleanup.
- Dedupe scan algorithm changes.
- Dedupe API response changes.
- Broad schema registry redesign.

## Technical Notes

- Target file: `app/domains/playback/dedupe_dao.py`.
- Existing tests: `tests/test_dedupe_schema_bootstrap_registry.py`.
- Shared helper: `app/infra/db/schema_bootstrap.py::ensure_registered_table`.
