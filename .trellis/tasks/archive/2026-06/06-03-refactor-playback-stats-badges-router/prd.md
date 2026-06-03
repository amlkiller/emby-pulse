# Refactor Playback Stats Badges Router

## Goal

Continue the P2 architecture audit work by extracting `GET /api/stats/badges` from `app/domains/playback/stats.py` into a focused playback-domain child router, reducing the mixed-responsibility stats module while preserving behavior.

## Requirements

- Extract `GET /api/stats/badges` into a new playback child router module.
- Include the child router from `app/domains/playback/stats.py` at the original route position, after `/api/stats/top_users_list` and before `/api/stats/monthly_stats`.
- Preserve `app.domains.playback.stats.api_badges` as a compatibility export for existing internal callers and tests.
- Preserve monkeypatch behavior by resolving old `stats` module globals at call time through provider callables for:
  - `check_login`
  - `build_stats_base_filter`
  - `get_playback_column_name`
  - `playback_store`
- Keep route URL, request parameters, response shapes, login/user scoping, SQL, badge thresholds, badge payloads, and exception fallback behavior unchanged.
- Add or update focused boundary tests for child router inclusion, compatibility export, route ordering, permission short-circuiting, and old-module monkeypatch behavior.

## Acceptance Criteria

- `app/domains/playback/stats.py` is smaller and delegates badges route handling to a new child router module.
- `/api/stats/badges` remains present under `stats.router`.
- `app.domains.playback.stats.api_badges` remains the same function object as the new child router export.
- The route order remains `/api/stats/top_users_list` -> `/api/stats/badges` -> `/api/stats/monthly_stats`.
- Existing tests that monkeypatch `stats.check_login`, `stats.build_stats_base_filter`, `stats.get_playback_column_name`, or `stats.playback_store` still pass.
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

Follow the existing playback child-router/provider pattern used by prior `stats.py` splits. The new module should own the moved route handler and dependency providers. `stats.py` should import the handler for compatibility, configure providers with lambdas that resolve current `stats` globals at request time, and include the child router exactly where the original route handler was declared.

## Out of Scope

- Do not refactor `/api/stats/monthly_stats`, dashboard cache endpoints, system monitor, item detail, DAO/query logic, or lifecycle behavior in this slice.
- Do not change badge thresholds, badge copy, item counting, time parsing, or fallback response shapes.
- Do not change database schema or external client adapters.

## Technical Notes

- Relevant audit item: `docs/架构审计.md` P2 issue 5, large mixed-responsibility domain files.
- Relevant specs:
  - `.trellis/spec/backend/directory-structure.md`
  - `.trellis/spec/backend/quality-guidelines.md`
  - `.trellis/spec/backend/error-handling.md`
- Existing compatibility patterns:
  - `app/domains/playback/top_users_router.py`
  - `app/domains/playback/poster_router.py`
  - `app/domains/playback/chart_router.py`
