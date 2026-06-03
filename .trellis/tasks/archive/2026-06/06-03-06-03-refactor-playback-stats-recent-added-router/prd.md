# Refactor Playback Stats Recent Added Router

## Background

`docs/架构审计.md` P2 item 5 calls out large mixed-responsibility domain files as a continuing architecture risk. `app/domains/playback/stats.py` has already been reduced through route-level child routers, but it still owns several unrelated endpoint groups.

## Goal

Extract `GET /api/stats/recent_added` from `app/domains/playback/stats.py` into a domain-local child router module while preserving behavior and compatibility.

## Scope

- Add `app/domains/playback/recent_added_router.py`.
- Move only `api_recent_added` into the new module.
- Include the child router from `app/domains/playback/stats.py` at the current route position, after the monthly stats router and before dashboard aggregate endpoints.
- Keep `stats.api_recent_added` available as a compatibility export.
- Preserve old-module monkeypatch behavior by resolving `check_login` and `_get_added_stats_sync` through provider callables configured by `stats.py`.
- Add focused boundary tests for route inclusion, compatibility export, login denial, and provider-based success behavior.

## Non-Goals

- Do not change `_get_added_stats_sync` implementation.
- Do not refactor dashboard cache endpoints in this slice.
- Do not change response shapes, auth rules, route URLs, route methods, or cache behavior.

## Acceptance Criteria

- `GET /api/stats/recent_added` is served by the new child router.
- The route remains ordered after `/api/stats/monthly_stats` and before `/api/dashboard/preload_status`.
- `app.domains.playback.stats.api_recent_added` is the same function as `app.domains.playback.recent_added_router.api_recent_added`.
- Unauthenticated request with a `Request` object returns `{"status": "error", "message": "请先登录"}` without calling `_get_added_stats_sync`.
- Internal call with `request=None` still skips login and returns `{"status": "success", "data": result}`.
- Monkeypatching `stats.check_login` and `stats._get_added_stats_sync` affects `stats.api_recent_added` at call time.
