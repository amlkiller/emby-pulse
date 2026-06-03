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


## Session 133: Refactor media requests safe media router

**Date**: 2026-06-03
**Task**: Refactor media requests safe media router
**Branch**: `main`

### Summary

Extracted safe media list endpoints into app/domains/media_requests/safe_media_router.py, included the child router from media_requests/router.py at the original route position, and preserved media_requests.router compatibility exports. Verified compile/import route checks, git diff checks, focused media request tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `ad1f85c` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 134: Refactor media requests discovery router

**Date**: 2026-06-03
**Task**: Refactor media requests discovery router
**Branch**: `main`

### Summary

Extracted media request discovery and browse endpoints into app/domains/media_requests/discovery_router.py, included the child router from media_requests/router.py at the original route position, and preserved media_requests.router compatibility exports for discovery routes and helper functions. Verified compile/import route checks, git diff checks, focused media request boundary tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `d7c30f9` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 135: Refactor media requests management router

**Date**: 2026-06-03
**Task**: Refactor media requests management router
**Branch**: `main`

### Summary

Extracted media request management and approval endpoints into app/domains/media_requests/management_router.py, included the child router from media_requests/router.py at the original route position, and preserved media_requests.router compatibility exports for management routes and models. Verified compile/import route checks, git diff checks, focused media request boundary tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `4a2f5c6` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 136: Refactor media requests registration router

**Date**: 2026-06-03
**Task**: Refactor media requests registration router
**Branch**: `main`

### Summary

Extracted the media request registration endpoint into app/domains/media_requests/registration_router.py, included the child router from media_requests/router.py at the original route position, and preserved media_requests.router compatibility exports for the registration route, model, and helper. Verified compile/import route checks, git diff checks, focused media request boundary tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `450fbc2` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 137: Refactor media requests user series router

**Date**: 2026-06-03
**Task**: Refactor media requests user series router
**Branch**: `main`

### Summary

Extracted the media request user series endpoints into app/domains/media_requests/user_series_router.py, included the child router from media_requests/router.py at the original route position, and preserved media_requests.router compatibility exports for the moved helpers and route handlers. Verified compile/import route checks, git diff checks, focused media request boundary tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `468acfa` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 138: Refactor media requests update router

**Date**: 2026-06-03
**Task**: Refactor media requests update router
**Branch**: `main`

### Summary

Extracted the media request update endpoints into app/domains/media_requests/update_router.py, included the child router from media_requests/router.py at the original route position, and preserved media_requests.router compatibility exports for the moved update model, helper, and route handlers. Verified compile/import route checks, git diff checks, focused media request boundary tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `fa3dcab` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 139: Refactor media requests submit router

**Date**: 2026-06-03
**Task**: Refactor media requests submit router
**Branch**: `main`

### Summary

Extracted the media request submit endpoint into app/domains/media_requests/submit_router.py, included the child router from media_requests/router.py at the original route position, and preserved media_requests.router compatibility exports for the moved submit model and route handler. Verified compile/import route checks, git diff checks, focused media request boundary tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `e00dde2` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 140: Refactor playback stats libraries router

**Date**: 2026-06-03
**Task**: Refactor playback stats libraries router
**Branch**: `main`

### Summary

Extracted the playback stats libraries endpoint into app/domains/playback/libraries_router.py, included the child router from playback/stats.py at the original route position, and preserved playback.stats compatibility export and monkeypatch behavior for the moved route. Verified compile/import route checks, git diff checks, focused playback stats boundary tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `f1c6f43` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 141: Refactor playback stats latest router

**Date**: 2026-06-03
**Task**: Refactor playback stats latest router
**Branch**: `main`

### Summary

Extracted the playback stats latest-media endpoint into app/domains/playback/latest_router.py, included the child router from playback/stats.py at the original route position, and preserved playback.stats compatibility export plus old-module monkeypatch behavior for login, admin user lookup, media API, TMDB client, and proxy provider access. Verified compile checks, import/route compatibility, git diff checks, focused playback stats boundary tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `e439d14` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 142: Refactor playback stats live router

**Date**: 2026-06-03
**Task**: Refactor playback stats live router
**Branch**: `main`

### Summary

Extracted the playback stats live session endpoints into app/domains/playback/live_router.py, included the child router from playback/stats.py at the original route position, and preserved playback.stats compatibility exports plus old-module monkeypatch behavior for user_service and media_api. Verified compile checks, import/route compatibility, git diff checks, focused playback stats boundary tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `1b5c560` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 143: Refactor playback stats top movies router

**Date**: 2026-06-03
**Task**: Refactor playback stats top movies router
**Branch**: `main`

### Summary

Extracted the playback stats top-movies endpoint into app/domains/playback/top_movies_router.py, included the child router from playback/stats.py at the original route position, and preserved playback.stats compatibility export plus old-module monkeypatch behavior for login, stats filter, playback store, clean-name helper, poster resolver, and logger access. Verified compile checks, import/route compatibility, git diff checks, focused playback stats boundary tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `bb241a4` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 144: Refactor playback stats user details router

**Date**: 2026-06-03
**Task**: Refactor playback stats user details router
**Branch**: `main`

### Summary

Extracted the playback stats user-details endpoint into app/domains/playback/user_details_router.py, included the child router from playback/stats.py at the original route position, and preserved playback.stats compatibility export plus old-module monkeypatch behavior for login, stats filter, playback column lookup, playback store, user map, clean-name helper, poster resolver, and media API access. Verified compile checks, import/route compatibility, git diff checks, focused playback stats boundary tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `1a3d560` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 145: Refactor playback stats chart router

**Date**: 2026-06-03
**Task**: Refactor playback stats chart router
**Branch**: `main`

### Summary

Extracted the playback stats chart/trend endpoint into app/domains/playback/chart_router.py, included the child router from playback/stats.py at the original route position, preserved playback.stats compatibility export and old-module monkeypatch behavior for login, stats filter, and playback store access, and verified compile checks, import/route compatibility, git diff checks, focused boundary tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `6043a58` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 146: Refactor playback stats poster router

**Date**: 2026-06-03
**Task**: Refactor playback stats poster router
**Branch**: `main`

### Summary

Extracted the playback stats poster_data endpoint into app/domains/playback/poster_router.py, included the child router from playback/stats.py at the original route position, preserved playback.stats compatibility export and old-module monkeypatch behavior for login, stats filter, playback store, media API, clean-name, and poster resolution dependencies, and verified compile checks, import/route compatibility, git diff checks, focused boundary tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `607caa0` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 147: Refactor playback stats top users router

**Date**: 2026-06-03
**Task**: Refactor playback stats top users router
**Branch**: `main`

### Summary

Extracted the playback stats top_users_list endpoint into app/domains/playback/top_users_router.py, included the child router from playback/stats.py at the original route position, preserved playback.stats compatibility export and old-module monkeypatch behavior for admin checks, stats filter, playback store, user map, and hidden-user settings, and verified compile checks, import/route compatibility, git diff checks, focused boundary tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `143b96c` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 148: Refactor playback stats badges router

**Date**: 2026-06-03
**Task**: Refactor playback stats badges router
**Branch**: `main`

### Summary

Extracted the playback stats badges endpoint into app/domains/playback/badges_router.py, included the child router from playback/stats.py at the original route position, preserved playback.stats compatibility export and old-module monkeypatch behavior for login, stats filter, playback column selection, and playback store dependencies, and verified compile checks, import/route compatibility, git diff checks, focused boundary tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `c1b2025` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 149: Refactor playback stats monthly router

**Date**: 2026-06-03
**Task**: Refactor playback stats monthly router
**Branch**: `main`

### Summary

Extracted the playback stats monthly_stats endpoint into app/domains/playback/monthly_router.py, included the child router from playback/stats.py at the original route position, preserved playback.stats compatibility export and old-module monkeypatch behavior for login, stats filter, and playback store dependencies, and verified compile checks, import/route compatibility, git diff checks, focused boundary tests, and the full test suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `82895f9` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 150: Refactor playback stats recent_added router

**Date**: 2026-06-03
**Task**: Refactor playback stats recent_added router
**Branch**: `main`

### Summary

Extracted the playback stats recent_added endpoint into app/domains/playback/recent_added_router.py, included the child router from playback/stats.py at the original route position, preserved playback.stats compatibility export and runtime monkeypatch behavior for check_login and _get_added_stats_sync providers, and verified compile checks, route/import compatibility, git diff checks, focused boundary tests, and the full pytest suite.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `8ae9101` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
