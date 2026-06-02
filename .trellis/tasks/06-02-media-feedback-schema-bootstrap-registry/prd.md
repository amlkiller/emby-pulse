# Media feedback schema bootstrap registry

## Goal

Continue the P2 schema fact-source cleanup from `docs/架构审计.md` by routing the registry-owned `media_feedback` bootstrap in `app.domains.media_requests.media_request_dao.ensure_media_request_schema()` through `app.infra.db.schema_bootstrap.ensure_registered_table(...)`.

## Requirements

- `ensure_media_request_schema()` must create `media_feedback` from `TABLE_SCHEMAS["media_feedback"]` through `ensure_registered_table(...)`.
- The `poster_path` column must remain present on fresh and legacy `media_feedback` tables.
- Existing media feedback DAO read/write behavior must remain unchanged.
- Keep the existing high-risk `media_requests` and `request_users` rebuild/migration logic local in this task.
- Add focused regression coverage proving registry-backed `media_feedback` creation, legacy `poster_path` upgrade behavior, DAO smoke paths, and no local duplicate `media_feedback` DDL/ALTER in the DAO.
- Update backend database guidelines with the `media_feedback` bootstrap contract.

## Acceptance Criteria

- [ ] `media_request_dao.ensure_media_request_schema()` contains no local `CREATE TABLE IF NOT EXISTS media_feedback` DDL.
- [ ] `media_request_dao.ensure_media_request_schema()` contains no local `ALTER TABLE media_feedback ADD COLUMN poster_path` statement.
- [ ] A fresh temporary system database creates `media_feedback` with registered columns after `ensure_media_request_schema()`.
- [ ] A legacy `media_feedback` table missing `poster_path` is upgraded by the registry-backed bootstrap path.
- [ ] Feedback create/list/update/delete DAO smoke paths still work.
- [ ] Focused media-feedback/schema registry tests, compile/import checks, ruff checks for changed files, `git diff --check`, and full pytest suite pass.

## Definition of Done

- Tests added or updated for changed behavior.
- Changed Python files compile through `uv run --with-requirements requirements.txt`.
- Ruff critical checks pass for changed Python files.
- Full pytest suite passes.
- Work is committed as one coherent schema-registry slice, then the task is archived and journaled.

## Technical Approach

Use the existing `schema_bootstrap.ensure_registered_table(cursor, "media_feedback")` helper inside `ensure_media_request_schema()`. To preserve legacy `poster_path` upgrades, add `media_feedback` safe ALTER metadata to `TABLE_ALTERS` if it is not already registered. Keep `media_requests` and `request_users` migration/rebuild logic untouched because those paths have compatibility semantics beyond simple CREATE/ALTER.

## Out of Scope

- Refactoring `media_requests` table rebuild logic.
- Refactoring `request_users` legacy unique-index migration logic.
- Changing media request or feedback route payloads.
- Migrating point game tables, invitations, sys license, Telegram bindings, or playback compatibility DDL.

## Technical Notes

- `docs/架构审计.md` P2 identifies schema fact-source split as a current cleanup area.
- `app.infra.db.schema_registry` already owns `media_feedback` table creation.
- Current local duplicate `media_feedback` DDL and local `poster_path` ALTER were found in `app.domains.media_requests.media_request_dao.ensure_media_request_schema()`.
