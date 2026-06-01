# Remove Deprecated Compatibility Files

## Goal

Delete the temporary compatibility files left after the database boundary refactor so new code cannot keep importing deprecated `app.core` database entrypoints.

## Requirements

- Remove the `app/core/database.py` compatibility shell that re-exports `app.infra.db.database`.
- Remove the `app/core/db_manager.py` compatibility shell that re-exports `app.infra.db.db_manager`.
- Verify no application or test code imports those deprecated modules before and after deletion.
- Keep unrelated dirty files untouched.

## Acceptance Criteria

- [x] `app/core/database.py` no longer exists.
- [x] `app/core/db_manager.py` no longer exists.
- [x] `rg` finds no references to `app.core.database` or `app.core.db_manager` in `app` or `tests`.
- [x] Tests still pass.

## Definition of Done

- Use `uv run --with-requirements requirements.txt ...` for Python/test commands.
- Commit only files belonging to this cleanup task.

## Out of Scope

- Do not delete unrelated local docs or Trellis spec files.
- Do not continue architecture refactoring beyond removing these deprecated compatibility files.

## Technical Notes

- `app/core/database.py` and `app/core/db_manager.py` have already been removed from the current worktree.
- `rg -n "app\.core\.database|app\.core\.db_manager" app tests --glob "*.py"` returned no matches.
- `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v` passed with `68 passed, 2 warnings`.
