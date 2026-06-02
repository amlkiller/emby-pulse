# Batch Media Request Schema Registry Checks

## Goal

Continue the schema-registry refactor by moving media-request table bootstrap paths to the shared registry in one coherent batch, then run one consolidated verification pass.

## Scope

- Route `media_requests` and `request_users` normal table creation through `app.infra.db.schema_bootstrap.ensure_registered_table(...)`.
- Preserve legacy high-risk rebuild migrations in `ensure_media_request_schema()`:
  - existing `media_requests` tables whose primary key does not include `season`;
  - existing `request_users` tables whose unique key does not include `season`.
- Remove local duplicate `CREATE TABLE` and compatible `ALTER TABLE` SQL for registry-owned media-request tables from DAO and database bootstrap paths.
- Update focused tests and database spec guidance to reflect the new registry-backed media-request bootstrap behavior.
- Batch verification: run focused tests, compile, ruff, `git diff --check`, and the full pytest suite once after the batch.

## Non-Goals

- Do not change request submission/listing/status behavior.
- Do not redesign high-risk data migration semantics beyond recreating legacy shapes from registry metadata.
- Do not split this work into one PRD/check/commit per table.

## Acceptance Criteria

- `ensure_media_request_schema()` uses registry metadata for normal `media_requests`, `request_users`, and `media_feedback` table creation.
- Registry-owned compatible `media_requests` optional columns come from `TABLE_ALTERS`, not local DAO `ALTER TABLE` copies.
- `_create_system_tables()` and `init_db()` no longer keep local `media_requests` table DDL.
- Focused tests cover:
  - fresh registry-backed `media_requests` / `request_users` creation;
  - registered optional-column ALTER application on legacy `media_requests`;
  - preservation of legacy rebuild migrations;
  - absence of duplicate local media-request DDL/ALTER in bootstrap paths.
- Consolidated verification passes before committing.
