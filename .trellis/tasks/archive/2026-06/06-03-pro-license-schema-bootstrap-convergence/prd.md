# Pro License Schema Bootstrap Convergence

## Goal

Move `app/domains/system/pro_license_dao.py` off local schema-registry execution logic and onto the shared `app.infra.db.schema_bootstrap.ensure_registered_table()` helper, reducing the schema fact-source split identified in `docs/架构审计.md`.

## Requirements

- Replace direct `TABLE_SCHEMAS` / `TABLE_ALTERS` usage in `pro_license_dao.py` with `ensure_registered_table()`.
- Remove local optional-column ALTER execution logic from the DAO.
- Preserve idempotent initialization of the registry-owned `sys_license` table.
- Preserve nullable Pro license extension columns such as `pro_token`, `expire_date`, `last_checked`, `max_devices`, and `current_devices`.
- Keep license read/write behavior unchanged.
- Update focused schema tests to assert the DAO uses the shared schema bootstrap helper and no local DDL/ALTER execution.

## Acceptance Criteria

- [ ] `ensure_pro_schema()` still creates the `sys_license` table.
- [ ] Registered `sys_license` alters still apply to a legacy table.
- [ ] Existing DAO read/write paths work after schema initialization.
- [ ] `pro_license_dao.py` imports `ensure_registered_table` and does not import `TABLE_SCHEMAS` / `TABLE_ALTERS`.
- [ ] Focused Pro license schema tests pass.
- [ ] Full `uv run pytest tests/ -v` passes before committing.

## Definition of Done

- Behavior-preserving schema bootstrap refactor only.
- Verification commands use `uv run`.
- Spec updates are made only if this task changes durable schema-bootstrap conventions.
- Work commit is created before Trellis archive and journal commits.

## Out of Scope

- Pro license validation or activation behavior changes.
- Public facade or wrapper cleanup.
- Broad schema registry redesign.
- Changes to other system-domain DAOs.

## Technical Notes

- Audit source: `docs/架构审计.md` P2 issue 4, schema fact-source split.
- Target file: `app/domains/system/pro_license_dao.py`.
- Existing focused tests: `tests/test_pro_license_schema_bootstrap_registry.py`.
- Shared helper: `app/infra/db/schema_bootstrap.py::ensure_registered_table`.
