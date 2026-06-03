# Refactor Playback Stats Top Movies Router

## Goal

Continue the P2 architecture audit work by extracting the `GET /api/stats/top_movies` endpoint from `app/domains/playback/stats.py` into a focused playback-domain child router, reducing mixed responsibilities while preserving behavior.

## Requirements

- Extract `GET /api/stats/top_movies` into a new playback child router module.
- Include the child router from `app/domains/playback/stats.py` at the original route position, after live session routes and before `/api/stats/user_details`.
- Preserve `app.domains.playback.stats.api_top_movies` as a compatibility export for existing internal callers and tests.
- Preserve monkeypatch behavior by resolving old `stats` module globals at call time through provider callables for:
  - `check_login`
  - `build_stats_base_filter`
  - `playback_store`
  - `get_clean_name`
  - `resolve_poster_ids`
  - `logger`
- Keep route URL, request parameters, response shapes, user scoping, period filters, SQL text shape, aggregation behavior, sorting, poster resolution, logging, and exception fallback behavior unchanged.
- Add or update focused boundary tests for child router inclusion, compatibility export, route ordering, permission short-circuiting, and old-module monkeypatch behavior.

## Acceptance Criteria

- `app/domains/playback/stats.py` is smaller and delegates `/api/stats/top_movies` to a new child router module.
- `/api/stats/top_movies` remains present under `stats.router`.
- `app.domains.playback.stats.api_top_movies` remains the same function object as the new child router export.
- The route order remains `/api/live` -> `/api/stats/top_movies` -> `/api/stats/user_details`.
- Existing tests that monkeypatch `stats.check_login`, `stats.playback_store`, or related helpers still pass.
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

Follow the existing playback child-router/provider pattern used by `libraries_router.py`, `latest_router.py`, and `live_router.py`. The new module should own the moved route handler and dependency providers. `stats.py` should import the handler for compatibility, configure providers with lambdas that resolve current `stats` globals at request time, and include the child router exactly where the original route handler was declared.

## Out of Scope

- Do not refactor `/api/stats/user_details`, chart/trend, poster data, badges, dashboard cache endpoints, system monitor, item detail, DAO/query logic, or lifecycle behavior in this slice.
- Do not change ranking semantics, hidden-user behavior, media type filters, period filters, or poster resolution behavior.
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
