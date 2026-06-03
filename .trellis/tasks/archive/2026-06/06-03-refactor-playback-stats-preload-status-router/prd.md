# Refactor Playback Stats Preload Status Router

## Background

`docs/架构审计.md` P2 item 5 identifies large mixed-responsibility domain files as a maintenance risk. `app/domains/playback/stats.py` has been reduced through route-level child routers, but it still owns dashboard cache endpoints inline.

## Goal

Extract `GET /api/dashboard/preload_status` from `app/domains/playback/stats.py` into a domain-local child router while preserving behavior and compatibility.

## Scope

- Add `app/domains/playback/preload_status_router.py`.
- Move only `api_preload_status` into the new module.
- Include the child router from `app/domains/playback/stats.py` at the current route position, after dashboard cache helpers and before dashboard cache task lifecycle functions.
- Keep `stats.api_preload_status` available as a compatibility export.
- Preserve old-module monkeypatch behavior by resolving dependencies through provider callables configured by `stats.py`:
  - `user_service`
  - `_get_dashboard_cache_entry`
  - `_DASHBOARD_PRELOAD_KEY`
  - `_DASHBOARD_CACHE_TTL`
  - `time`

## Non-Goals

- Do not change response shapes, admin auth rules, route URL, route method, cache age calculation, or count fields.
- Do not refactor `/api/dashboard/init`, dashboard cache task lifecycle, item detail, or `_get_added_stats_sync` in this slice.

## Acceptance Criteria

- `GET /api/dashboard/preload_status` is served by the new child router.
- The route remains ordered after `/api/stats/recent_added` and before `/api/dashboard/init`.
- `app.domains.playback.stats.api_preload_status` is the same function as `app.domains.playback.preload_status_router.api_preload_status`.
- Non-admin requests return `{"status": "error", "message": "需要管理员权限"}` before reading dashboard cache state.
- Admin requests preserve `cached`, `cache_age`, `cache_ttl`, `libraries_count`, and `users_count` response semantics.
- Monkeypatching the old `stats.*` dependencies affects `stats.api_preload_status` at call time.
