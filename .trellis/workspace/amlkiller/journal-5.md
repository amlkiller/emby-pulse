# Journal - amlkiller (Part 5)

> Continuation from `journal-4.md` (archived at ~2000 lines)
> Started: 2026-06-04

---



## Session 240: Extract users delete route

**Date**: 2026-06-04
**Task**: Extract users delete route
**Branch**: `main`

### Summary

Extracted DELETE /api/manage/user/{user_id} into app/domains/users/delete_router.py, preserved users/router.py compatibility export and legacy monkeypatch providers, and added regression coverage for route order plus login/admin/health/password-verification short-circuit behavior. Verification: compileall for changed files, import compatibility check, focused users tests 25 passed with 2 warnings, full suite 902 passed with 3 warnings.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `5edfc3c` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 241: Extract users new route

**Date**: 2026-06-04
**Task**: Extract users new route
**Branch**: `main`

### Summary

Extracted POST /api/manage/user/new and NewUserModelEx into app/domains/users/new_user_router.py, preserved users/router.py compatibility exports and legacy monkeypatch providers, and added regression coverage for route order plus admin/health short-circuit and success mapping behavior. Verification: compileall for changed files, import compatibility check, focused users tests 26 passed with 2 warnings, full suite 905 passed with 3 warnings.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `2833907` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
