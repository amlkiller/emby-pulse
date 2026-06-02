# Remove Plugin Directory Ensure Redirects

## Goal

Remove private plugin helper methods that only redirect to `os.makedirs(...)`.

## Scope

- Inline `CoverGeneratorPlugin._ensure_dir()` call sites to `os.makedirs(OUTPUT_DIR, exist_ok=True)`.
- Inline `UserBackupPlugin._ensure_dir()` call sites to `os.makedirs(BACKUP_DIR, exist_ok=True)`.
- Delete the two pure redirect `_ensure_dir()` methods.
- Do not change `LibraryCoverPlugin._ensure_dir()` because it also initializes `mappings.json`.
- Do not change plugin lifecycle behavior beyond removing the redirect layer.

## Acceptance Criteria

- No `_ensure_dir()` helper remains in `cover_generator` or `user_backup`.
- Plugin construction and enable hooks still ensure their directories exist.
- Focused import/compile checks and the full test suite pass.
