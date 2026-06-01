# Refactor User Bot Schema Bootstrap Through Registry

## Goal

Reduce schema fact-source drift called out in `docs/架构审计.md` by routing the user-bot registry-owned bootstrap tables through `app.infra.db.schema_registry` instead of keeping duplicate table DDL in `app.domains.users.user_bot_dao`.

## Requirements

* `tg_user_bindings`, `tg_user_blacklist`, and `tg_reg_logs` must be created from `TABLE_SCHEMAS`.
* `tg_user_bindings` active columns `init_password`, `tg_username`, and `tg_display_name` must be represented by the registry and applied to legacy table shapes through `TABLE_ALTERS`.
* `tg_bot_users` and `tg_channel_bindings` stay as local DAO DDL because they are not registry-owned in this slice.
* Existing user-bot DAO behavior and query payloads must not change.
* The batch must include focused regression tests for registry-backed creation, legacy column migration, source guards against duplicate registry-owned DDL, and preservation of local non-registry table creation.

## Acceptance Criteria

* [x] `user_bot_dao.ensure_user_bot_tables()` creates registry-owned user-bot tables from `TABLE_SCHEMAS`.
* [x] `TABLE_SCHEMAS["tg_user_bindings"]` includes the columns used by runtime code: `init_password`, `tg_username`, and `tg_display_name`.
* [x] `TABLE_ALTERS["tg_user_bindings"]` migrates old `tg_user_bindings` tables missing those columns.
* [x] `tg_bot_users` and `tg_channel_bindings` are still created by `ensure_user_bot_tables()`.
* [x] Focused tests prove creation, legacy ALTER application, source ownership, and local-only table preservation.
* [x] Schema-registry regression tests and full pytest suite pass before commit.

## Definition of Done

* Tests added or updated for changed behavior.
* Changed Python files compile.
* Ruff passes for changed Python files.
* `git diff --check` passes.
* Full pytest suite passes.
* Work is committed as one coherent schema-registry slice.

## Technical Approach

Use the same pattern as recent gap, dedupe, and notification schema bootstrap refactors: import `TABLE_SCHEMAS` and `TABLE_ALTERS` in the DAO, execute registry-owned table DDL through those objects, and tolerate duplicate-column errors when replaying registered ALTER statements. Keep non-registry local tables unchanged to avoid expanding ownership beyond this slice.

## Decision (ADR-lite)

Context: `tg_user_bindings`, `tg_user_blacklist`, and `tg_reg_logs` are already listed as system tables in `schema_registry`, but `user_bot_dao` still had duplicate local DDL and local ALTER statements.

Decision: Move registry-owned table creation and user-binding ALTERs to `schema_registry`, while leaving unregistered helper tables local.

Consequences: Registry and small bootstrap paths stay aligned for the user-bot owned system tables. The remaining local tables can be considered in a future broader plugin/domain schema registration pass.

## Out of Scope

* Rewriting `app.infra.db.database._create_system_tables()`.
* Rebuilding or changing existing data in `tg_user_bindings`.
* Registering `tg_bot_users` or `tg_channel_bindings`.
* Refactoring Telegram bot service command behavior.

## Technical Notes

* `docs/架构审计.md` P2 identifies schema fact-source split as the current cleanup area.
* `.trellis/spec/backend/database-guidelines.md` requires small bootstrap helpers for registry-owned tables to use `TABLE_SCHEMAS` / `TABLE_ALTERS`.
* Current runtime code selects and updates `tg_username` and `tg_display_name` from `tg_user_bindings`, so the registry must include those active columns.
