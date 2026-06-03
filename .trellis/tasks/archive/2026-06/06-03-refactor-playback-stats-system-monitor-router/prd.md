# Refactor Playback Stats System Monitor Router

## Background

`docs/架构审计.md` P2 item 5 identifies large mixed-responsibility domain files as a maintenance risk. `app/domains/playback/stats.py` has been reduced by extracting route-level child routers, but it still owns unrelated endpoint groups inline.

## Goal

Extract `GET /api/system/monitor` from `app/domains/playback/stats.py` into a domain-local child router while preserving behavior and compatibility.

## Scope

- Add `app/domains/playback/system_monitor_router.py`.
- Move only `api_system_monitor` into the new module.
- Include the child router from `app/domains/playback/stats.py` at the current route position, after dashboard aggregate endpoints and before `/api/stats/item_detail`.
- Keep `stats.api_system_monitor` available as a compatibility export.
- Preserve old-module monkeypatch behavior by resolving dependencies through provider callables configured by `stats.py`:
  - `user_service`
  - `psutil`
  - `safe_error_message`

## Non-Goals

- Do not change response shapes, auth rules, route URL, route method, or metric calculations.
- Do not refactor dashboard cache, item detail, `_get_added_stats_sync`, or other playback stats endpoints in this slice.

## Acceptance Criteria

- `GET /api/system/monitor` is served by the new child router.
- The route remains ordered after `/api/dashboard/init` and before `/api/stats/item_detail`.
- `app.domains.playback.stats.api_system_monitor` is the same function as `app.domains.playback.system_monitor_router.api_system_monitor`.
- Non-admin requests return the existing admin-login error before calling `psutil` metrics.
- Admin requests return the same success payload keys for CPU, memory, and disk.
- Monkeypatching the old `stats.user_service`, `stats.psutil`, and `stats.safe_error_message` dependencies affects `stats.api_system_monitor` at call time.
