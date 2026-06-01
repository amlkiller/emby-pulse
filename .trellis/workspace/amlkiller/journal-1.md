# Journal - amlkiller (Part 1)

> AI development session journal
> Started: 2026-05-29

---

2026-05-31: Started backend modular refactor. Split `app/main.py` into `app/bootstrap/*` modules for runtime prep, database init, logging, middleware, route registration, and user portal isolation. Verified with `uv run --with-requirements requirements.txt` syntax/import checks and `pytest` (68 passed). Updated backend directory-structure and error-handling specs to reflect the new bootstrap boundary.



## Session 1: Backend modular refactor

**Date**: 2026-05-31
**Task**: Backend modular refactor
**Branch**: `main`

### Summary

Split app/main.py into app/bootstrap modules, kept behavior stable, and documented the new bootstrap boundary.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `4113e66` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete

---

2026-06-01: Continued architecture refactor. Moved `user_backup` plugin DB access behind `app.dao.user_backup_dao`, moved history local IP lookup behind `app.infra.db.local_playback_store`, and moved startup session cleanup into `app.dao.session_dao`. Verified with `uv run --with-requirements requirements.txt` compile/import checks and full pytest (`68 passed, 4 warnings`).

Note for the next conversation: always use `uv run --with-requirements requirements.txt` for Python commands in this repo, and set `PYTHONIOENCODING=utf-8` on Windows when command output may include Chinese text.


## Session 2: Database boundary refactor wrap-up

**Date**: 2026-06-01
**Task**: Database boundary refactor wrap-up
**Branch**: `main`

### Summary

Completed the infra database boundary refactor, removed the legacy query_db facade, moved DB core and manager into infra, verified tests, and recorded the uv run convention in docs.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `e632c2b` | (see git log) |
| `0b6fb0a` | (see git log) |
| `f1338d6` | (see git log) |
| `de62860` | (see git log) |
| `112b5c7` | (see git log) |
| `2f5372f` | (see git log) |
| `d3f2756` | (see git log) |
| `cf093c3` | (see git log) |
| `cb9f08b` | (see git log) |
| `6379ed1` | (see git log) |
| `d1315e0` | (see git log) |
| `5a4468d` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
