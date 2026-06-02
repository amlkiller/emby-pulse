# Auth Local Users Schema Bootstrap Convergence

## Goal

Move `app/domains/users/auth_dao.py` off local schema-registry execution logic and onto the shared `app.infra.db.schema_bootstrap.ensure_registered_table()` helper, reducing the schema fact-source split identified in `docs/架构审计.md`.

## Requirements

- Replace direct `TABLE_SCHEMAS` / `TABLE_ALTERS` usage in `auth_dao.ensure_local_users_table()` with `ensure_registered_table()`.
- Remove the local `_apply_table_alters()` helper and `sqlite3` dependency from the DAO.
- Preserve idempotent initialization of the registry-owned `local_users` table.
- Preserve safe optional-column ALTER application for legacy `local_users` tables.
- Do not add unsafe identity/base columns such as `username`, `password_hash`, `created_at`, or `updated_at` through generic ALTER metadata.
- Keep login, local-user management, and TOTP DAO behavior unchanged.
- Update focused schema tests to assert the DAO uses the shared schema bootstrap helper and no local DDL/ALTER execution.

## Acceptance Criteria

- [ ] `ensure_local_users_table()` still creates the `local_users` table.
- [ ] Registered safe optional `local_users` alters still apply to a legacy table.
- [ ] TOTP DAO paths continue to work after schema initialization.
- [ ] `auth_dao.py` imports `ensure_registered_table` and does not import `TABLE_SCHEMAS` / `TABLE_ALTERS`.
- [ ] Focused auth local-users schema tests pass.
- [ ] Full `uv run pytest tests/ -v` passes before committing.

## Definition of Done

- Behavior-preserving schema bootstrap refactor only.
- Verification commands use `uv run`.
- Spec updates are made only if this task changes durable schema-bootstrap conventions.
- Work commit is created before Trellis archive and journal commits.

## Out of Scope

- Login authentication behavior changes.
- TOTP feature changes.
- Local-user route/API changes.
- Wrapper/pass-through cleanup.
- Broad schema registry redesign.

## Technical Notes

- Audit source: `docs/架构审计.md` P2 issue 4, schema fact-source split.
- Target file: `app/domains/users/auth_dao.py`.
- Existing focused tests: `tests/test_auth_local_users_schema_bootstrap_registry.py`.
- Shared helper: `app/infra/db/schema_bootstrap.py::ensure_registered_table`.
- `ensure_registered_table()` supports registered optional ALTER application and does not invent unregistered unsafe columns.
