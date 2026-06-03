# Refactor Playback Stats Recent Activity Router

## Background

`docs/架构审计.md` P2 item 5 identifies large mixed-responsibility domain files as a maintenance risk. `app/domains/playback/stats.py` has already been reduced through several child routers, but it still owns unrelated playback stats endpoints inline.

## Goal

Extract `GET /api/stats/recent` from `app/domains/playback/stats.py` into a domain-local child router while preserving behavior and compatibility.

## Scope

- Add `app/domains/playback/recent_activity_router.py`.
- Move only `api_recent_activity` into the new module.
- Include the child router from `app/domains/playback/stats.py` at the current route position, after `/api/stats/libraries` and before `/api/stats/latest`.
- Keep `stats.api_recent_activity` available as a compatibility export.
- Preserve old-module monkeypatch behavior by resolving dependencies through provider callables configured by `stats.py`:
  - `check_login`
  - `build_stats_base_filter`
  - `playback_store`
  - `get_user_map_local`
  - `media_api`

## Non-Goals

- Do not change SQL, response shapes, auth rules, route URLs, route methods, image-tag lookup behavior, or non-admin `UserId` stripping.
- Do not refactor dashboard cache, item detail, system monitor, or `_get_added_stats_sync` in this slice.

## Acceptance Criteria

- `GET /api/stats/recent` is served by the new child router.
- The route remains ordered after `/api/stats/libraries` and before `/api/stats/latest`.
- `app.domains.playback.stats.api_recent_activity` is the same function as `app.domains.playback.recent_activity_router.api_recent_activity`.
- Unauthenticated requests return `{"status": "error", "message": "请先登录"}` before query or media side effects.
- Non-admin requests keep the current user scoping behavior and strip `UserId` from returned rows.
- Monkeypatching the old `stats.*` dependencies affects `stats.api_recent_activity` at call time.
