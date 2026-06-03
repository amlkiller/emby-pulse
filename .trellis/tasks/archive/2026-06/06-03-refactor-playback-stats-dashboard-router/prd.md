# Refactor Playback Stats Dashboard Router

## Background

`docs/架构审计.md` P2 item 5 identifies large mixed-responsibility domain files as a maintenance risk. `app/domains/playback/stats.py` has been reduced through route-level child routers, but it still owns the basic playback stats dashboard endpoint inline.

## Goal

Extract `GET /api/stats/dashboard` from `app/domains/playback/stats.py` into a domain-local child router while preserving behavior and compatibility.

## Scope

- Add `app/domains/playback/dashboard_router.py`.
- Move only `api_dashboard` into the new module.
- Include the child router from `app/domains/playback/stats.py` at the current route position, before `/api/stats/libraries`.
- Keep `stats.api_dashboard` available as a compatibility export.
- Preserve old-module monkeypatch behavior by resolving dependencies through provider callables configured by `stats.py`:
  - `check_login`
  - `build_stats_base_filter`
  - `playback_store`
  - `get_cached_stats`
  - `set_cached_stats`
  - `media_api`

## Non-Goals

- Do not change SQL, response shapes, auth rules, route URL, route method, or cache key behavior.
- Do not refactor `/api/dashboard/init`, preload status, dashboard cache task lifecycle, item detail, or `_get_added_stats_sync` in this slice.

## Acceptance Criteria

- `GET /api/stats/dashboard` is served by the new child router.
- The route remains ordered before `/api/stats/libraries`.
- `app.domains.playback.stats.api_dashboard` is the same function as `app.domains.playback.dashboard_router.api_dashboard`.
- Unauthenticated requests return `{"status": "error", "message": "请先登录"}` before cache, query, or media side effects.
- Non-admin requests keep current user scoping behavior and cache key semantics.
- Cache hits return without query or media side effects.
- Cache misses preserve playback query order, library count fallback, and cache write behavior.
- Monkeypatching the old `stats.*` dependencies affects `stats.api_dashboard` at call time.
