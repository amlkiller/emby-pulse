# Refactor Playback Stats User Details Router

## Goal

Continue the P2 architecture audit work by extracting the `GET /api/stats/user_details` endpoint from `app/domains/playback/stats.py` into a focused playback-domain child router, reducing mixed responsibilities while preserving behavior.

## Requirements

- Extract `GET /api/stats/user_details` into a new playback child router module.
- Include the child router from `app/domains/playback/stats.py` at the original route position, after `/api/stats/top_movies` and before chart/trend routes.
- Preserve `app.domains.playback.stats.api_user_details` as a compatibility export for existing internal callers and tests.
- Preserve monkeypatch behavior by resolving old `stats` module globals at call time through provider callables for:
  - `check_login`
  - `build_stats_base_filter`
  - `get_playback_column_name`
  - `playback_store`
  - `get_user_map_local`
  - `get_clean_name`
  - `resolve_poster_ids`
  - `media_api`
- Keep route URL, request parameters, response shapes, user scoping, dynamic column detection, aggregation behavior, poster resolution, media API age lookup, and exception fallback behavior unchanged.
- Add or update focused boundary tests for child router inclusion, compatibility export, route ordering, permission short-circuiting, and old-module monkeypatch behavior.

## Acceptance Criteria

- `app/domains/playback/stats.py` is smaller and delegates `/api/stats/user_details` to a new child router module.
- `/api/stats/user_details` remains present under `stats.router`.
- `app.domains.playback.stats.api_user_details` remains the same function object as the new child router export.
- The route order remains `/api/stats/top_movies` -> `/api/stats/user_details` -> `/api/stats/chart`.
- Existing tests that monkeypatch `stats.check_login`, `stats.playback_store`, `stats.media_api`, or related helpers still pass.
- Verification passes:
  - `uv run python -m compileall` for changed Python files.
  - A `uv run python -c ...` import/route compatibility check with UTF-8 output on Windows if needed.
  - Focused playback stats boundary tests.
  - Full `uv run pytest tests/ -v`.

## Definition of Done

- Work commit is created for code/test changes.
- Trellis task is archived after the work commit.
- Session journal records the slice and verification summary using the work commit hash.

## Technical Approach

Follow the existing playback child-router/provider pattern used by `libraries_router.py`, `latest_router.py`, `live_router.py`, and `top_movies_router.py`. The new module should own the moved route handler and dependency providers. `stats.py` should import the handler for compatibility, configure providers with lambdas that resolve current `stats` globals at request time, and include the child router exactly where the original route handler was declared.

## Out of Scope

- Do not refactor chart/trend, poster data, badges, dashboard cache endpoints, system monitor, item detail, DAO/query logic, or lifecycle behavior in this slice.
- Do not change user details aggregation semantics, log limits, account-age lookup behavior, poster resolution behavior, or fallback response shapes.
- Do not change database schema or external client adapters.

## Technical Notes

- Relevant audit item: `docs/架构审计.md` P2 issue 5, large mixed-responsibility domain files.
- Relevant specs:
  - `.trellis/spec/backend/directory-structure.md`
  - `.trellis/spec/backend/quality-guidelines.md`
  - `.trellis/spec/backend/error-handling.md`
- Existing compatibility patterns:
  - `app/domains/playback/libraries_router.py`
  - `app/domains/playback/latest_router.py`
  - `app/domains/playback/live_router.py`
  - `app/domains/playback/top_movies_router.py`
