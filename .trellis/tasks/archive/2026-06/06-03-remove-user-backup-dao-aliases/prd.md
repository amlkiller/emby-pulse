# Remove User Backup DAO Aliases

## Goal

Remove user-backup DAO helpers that only forward to `app.domains.users.user_dao`
without adding backup-specific SQL, validation, transformation, or orchestration.

## Scope

- Replace user-backup plugin calls to:
  - `list_users_meta_for_backup()`
  - `get_user_meta_for_backup()`
  - `upsert_user_meta_for_backup()`
- Point those call sites directly at the real `user_dao` functions:
  - `user_dao.list_all_user_meta()`
  - `user_dao.get_user_meta(...)`
  - `user_dao.upsert_user_meta_fields(...)`
- Remove the three pure alias helpers from
  `app/plugins/user_backup/user_backup_dao.py`.

## Non-Goals

- Do not remove backup DAO functions that own backup-specific SQL or restore
  behavior, such as point-log and Telegram-binding backup helpers.
- Do not change backup file formats, restore modes, field mappings, or route
  responses.

## Acceptance Criteria

- No production caller references the three removed backup aliases.
- `user_backup_dao.py` keeps only functions that do real backup persistence or
  backup-specific queries.
- Changed Python files compile with `uv run`.
- The full test suite passes.
