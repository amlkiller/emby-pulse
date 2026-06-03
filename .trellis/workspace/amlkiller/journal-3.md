# Journal - amlkiller (Part 3)

> Continuation from `journal-2.md` (archived at ~2000 lines)
> Started: 2026-06-03

---



## Session 120: Refactor playback stats helpers

**Date**: 2026-06-03
**Task**: Refactor playback stats helpers
**Branch**: `main`

### Summary

Extracted playback stats cache, auth, item-name, poster-id, admin-user, and user-map helpers into app/domains/playback/stats_helpers.py while preserving stats.py compatibility exports. Verified compile/import checks, focused playback stats tests, and full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `a13ca5f` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 121: Refactor notification announcements router

**Date**: 2026-06-03
**Task**: Refactor notification announcements router
**Branch**: `main`

### Summary

Extracted notification announcement management and user announcement routes into app/domains/notifications/announcements_router.py, included the child router from messages.py, and preserved messages.py compatibility exports. Verified compile/import route checks, focused notification messages/schema tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `da34e50` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 122: Refactor users tag router

**Date**: 2026-06-03
**Task**: Refactor users tag router
**Branch**: `main`

### Summary

Extracted users tag constants, models, and management routes into app/domains/users/tag_router.py, included the child router from users/router.py at the original route position, and preserved users.router compatibility exports. Verified compile/import route checks, focused users router/public-service tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `f3753d0` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 123: Refactor users request permission router

**Date**: 2026-06-03
**Task**: Refactor users request permission router
**Branch**: `main`

### Summary

Extracted users request-permission model and management routes into app/domains/users/request_permission_router.py, included the child router from users/router.py before the tag router, and preserved users.router compatibility exports. Verified compile/import route checks, focused users router/public-service tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `6ca7385` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 124: Refactor users template router

**Date**: 2026-06-03
**Task**: Refactor users template router
**Branch**: `main`

### Summary

Extracted users default-template management routes into app/domains/users/template_router.py, included the child router from users/router.py at the original route position, and preserved users.router compatibility exports. Verified compile/import route checks, focused users router/public-service tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `38e8e16` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 125: Refactor users list router

**Date**: 2026-06-03
**Task**: Refactor users list router
**Branch**: `main`

### Summary

Extracted the standalone users list route into app/domains/users/list_router.py, included the child router from users/router.py at the original route position, and preserved users.router compatibility export. Verified compile/import route checks, focused users router/public-service tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `37d2d4b` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 126: Refactor users audit log router

**Date**: 2026-06-03
**Task**: Refactor users audit log router
**Branch**: `main`

### Summary

Extracted the users audit log management endpoints into app/domains/users/audit_log_router.py, included the child router from users/router.py at the original route position, and preserved users.router compatibility exports. Verified compile/import route checks, focused users router tests, git diff checks, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `b1dd178` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 127: Refactor users delete verification router

**Date**: 2026-06-03
**Task**: Refactor users delete verification router
**Branch**: `main`

### Summary

Extracted users delete-verification/admin-password endpoints into app/domains/users/delete_verification_router.py, included child routers at the original route positions around the audit log routes, and preserved users.router compatibility exports including APP_START_TIME behavior. Verified compile/import route checks, focused users tests, git diff checks, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `7debb8d` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 128: Refactor users invitation router

**Date**: 2026-06-03
**Task**: Refactor users invitation router
**Branch**: `main`

### Summary

Extracted users invitation-code management endpoints into app/domains/users/invitation_router.py, included the child router from users/router.py at the original route position, and preserved users.router compatibility exports plus existing monkeypatch behavior through dependency providers. Verified compile/import route checks, focused users invitation tests, git diff checks, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `c8d8de2` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 129: Refactor users library visibility router

**Date**: 2026-06-03
**Task**: Refactor users library visibility router
**Branch**: `main`

### Summary

Extracted C-side users library visibility endpoints into app/domains/users/library_visibility_router.py, included the child router from users/router.py at the original route position, and preserved users.router compatibility exports. Verified compile/import route checks, focused users tests, git diff checks, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `58e2c02` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 130: Refactor media requests auth router

**Date**: 2026-06-03
**Task**: Refactor media requests auth router
**Branch**: `main`

### Summary

Extracted user community authentication endpoints into app/domains/media_requests/auth_router.py, included the child router from media_requests/router.py at the original route position, and preserved media_requests.router compatibility exports for direct callers and monkeypatch-based tests. Verified compile/import route checks, git diff checks, focused media request tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `b7491d7` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 131: Refactor media requests feedback router

**Date**: 2026-06-03
**Task**: Refactor media requests feedback router
**Branch**: `main`

### Summary

Extracted media request feedback endpoints into app/domains/media_requests/feedback_router.py, included the child router from media_requests/router.py at the original route position, and preserved media_requests.router compatibility exports for direct callers and monkeypatch-based tests. Verified compile/import route checks, git diff checks, focused media request tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `5fbab57` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 132: Refactor media requests cache control router

**Date**: 2026-06-03
**Task**: Refactor media requests cache control router
**Branch**: `main`

### Summary

Extracted media request cache control endpoints and lifecycle wrappers into app/domains/media_requests/cache_control_router.py, included the child router from media_requests/router.py at the original route position, and preserved media_requests.router compatibility exports for bootstrap imports and monkeypatch-based tests. Verified compile/import route checks, git diff checks, focused media request and lifecycle tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `6ec0388` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
