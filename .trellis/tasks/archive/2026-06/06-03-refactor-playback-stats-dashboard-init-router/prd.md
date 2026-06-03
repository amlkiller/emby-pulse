# Refactor playback stats dashboard init router

## Goal

Split `GET /api/dashboard/init` out of `app/domains/playback/stats.py` into a playback domain child router while preserving the existing API contract and compatibility exports.

## Requirements

* Move only the dashboard init endpoint into `app/domains/playback/dashboard_init_router.py`.
* Keep the route path, method, async behavior, response shape, admin authorization behavior, cache behavior, timeout fallback behavior, and `UserId` stripping behavior unchanged.
* Keep `app.domains.playback.stats.api_dashboard_init` available as a compatibility export.
* Configure dashboard init dependencies from `stats.py` through provider lambdas so monkeypatches to legacy `stats.*` globals are observed at request time.
* Preserve route order: after `/api/dashboard/preload_status` and before `/api/system/monitor`.
* Add focused tests covering route inclusion, compatibility export, permission short-circuit, cache hit, cache miss, and timeout stale-cache fallback.

## Acceptance Criteria

* [ ] `stats.py` no longer defines the dashboard init endpoint inline.
* [ ] `dashboard_init_router.py` owns the endpoint and exposes `set_dependency_providers`.
* [ ] Existing and new playback stats facade tests pass.
* [ ] Full test suite passes.
* [ ] Code/test changes are committed separately from Trellis archive and journal bookkeeping.

## Definition of Done

* Compile changed Python files with `uv run python -m compileall`.
* Run focused tests for `tests/test_playback_stats_public_auth_facade_boundary.py`.
* Run `uv run pytest tests/ -v`.
* Run `git diff --check`.
* Commit the code/test slice.
* Archive the Trellis task and record the session journal.

## Technical Approach

Follow the existing child-router/provider pattern used by `dashboard_router.py`, `preload_status_router.py`, and other playback stats slices. Keep default providers pointing at current domain services, then override them in `stats.py` with lambdas that resolve legacy globals at call time.

## Out of Scope

* Splitting `/api/stats/item_detail`.
* Changing dashboard cache service internals.
* Changing response fields, error messages, or timeout values.
* Broad formatting or cleanup outside the touched slice.

## Technical Notes

* Architecture audit target: `docs/架构审计.md` P2 item 5, domain files still too large and mixed-responsibility.
* Applicable specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/backend/error-handling.md`, `.trellis/spec/guides/code-reuse-thinking-guide.md`.
