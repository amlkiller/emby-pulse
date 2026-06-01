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


## Session 3: Gap schema bootstrap registry

**Date**: 2026-06-02
**Task**: Gap schema bootstrap registry
**Branch**: `main`

### Summary

Routed gap schema bootstrap through schema_registry, added focused regression tests, updated database schema guidance, and verified full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `4e4aa55` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 4: Dedupe schema bootstrap registry

**Date**: 2026-06-02
**Task**: Dedupe schema bootstrap registry
**Branch**: `main`

### Summary

Routed dedupe schema bootstrap through schema_registry, preserved legacy whitelist migration, added focused regression tests, updated database schema guidance, and verified full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `0a4342f` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 5: Notification schema bootstraps registry

**Date**: 2026-06-02
**Task**: Notification schema bootstraps registry
**Branch**: `main`

### Summary

Routed selected notification and message schema bootstraps through schema_registry, preserved the request admin message index and announcement table exclusion, added focused regression tests, updated database guidance, and verified full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `edfae01` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 6: User bot schema registry bootstrap

**Date**: 2026-06-02
**Task**: User bot schema registry bootstrap
**Branch**: `main`

### Summary

Routed user-bot registry-owned tables through schema_registry, added tg_user_bindings ALTER coverage, preserved local helper tables, and verified with focused schema tests plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `e9ea546` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 7: Auth local users schema registry bootstrap

**Date**: 2026-06-02
**Task**: Auth local users schema registry bootstrap
**Branch**: `main`

### Summary

Routed auth local_users schema bootstrap through schema_registry, added TOTP columns and safe ALTER coverage, guarded unsafe SQLite ALTERs, and verified with focused schema tests plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `f094593` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 8: Pro license schema registry bootstrap

**Date**: 2026-06-02
**Task**: Pro license schema registry bootstrap
**Branch**: `main`

### Summary

Routed sys_license bootstrap through schema_registry, added nullable device extension columns and safe ALTER coverage, preserved Pro status behavior, and verified with focused schema tests plus full pytest.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `0e9e87e` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 9: Batch Archive Completed PRDs

**Date**: 2026-06-02
**Task**: Batch Archive Completed PRDs
**Branch**: `main`

### Summary

Validated all active PRDs as complete, ran unified checks, and archived 29 completed tasks in one batch commit.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `629911c` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
