# Refactor Playback Stats Top Users Router

## Goal

Continue the P2 architecture audit work by extracting `GET /api/stats/top_users_list` from `app/domains/playback/stats.py` into a focused playback-domain child router, reducing the mixed-responsibility stats module while preserving behavior.

## Requirements

- Extract `GET /api/stats/top_users_list` into a new playback child router module.
- Include the child router from `app/domains/playback/stats.py` at the original route position, after `/api/stats/poster_data` and before `/api/stats/badges`.
- Preserve `app.domains.playback.stats.api_top_users_list` as a compatibility export for existing internal callers and tests.
- Preserve monkeypatch behavior by resolving old `stats` module globals at call time through provider callables for:
  - `user_service`
  - `build_stats_base_filter`
  - `playback_store`
  - `get_user_map_local`
  - `get_hidden_users`
- Keep route URL, request parameters, response shapes, admin-only access check, period filtering, SQL, user-name mapping, hidden-user filtering, five-row cap, and exception fallback behavior unchanged.
- Add or update focused boundary tests for child router inclusion, compatibility export, route ordering, admin permission short-circuiting, and old-module monkeypatch behavior.

## Acceptance Criteria

- `app/domains/playback/stats.py` is smaller and delegates top-users list route handling to a new child router module.
- `/api/stats/top_users_list` remains present under `stats.router`.
- `app.domains.playback.stats.api_top_users_list` remains the same function object as the new child router export.
- The route order remains `/api/stats/poster_data` -> `/api/stats/top_users_list` -> `/api/stats/badges`.
- Existing tests that monkeypatch `stats.user_service`, `stats.build_stats_base_filter`, `stats.playback_store`, `stats.get_user_map_local`, or `stats.get_hidden_users` still pass.
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

- Do not refactor `/api/stats/badges`, dashboard cache endpoints, system monitor, item detail, DAO/query logic, or lifecycle behavior in this slice.
- Do not change top-users aggregation semantics, time-period filtering, hidden-user behavior, sorting, limit behavior, or fallback response shapes.
- Do not change database schema or external client adapters.

## Technical Notes

- Relevant audit item: `docs/架构审计.md` P2 issue 5, large mixed-responsibility domain files.
- Relevant specs:
  - `.trellis/spec/backend/directory-structure.md`
  - `.trellis/spec/backend/quality-guidelines.md`
  - `.trellis/spec/backend/error-handling.md`
- Existing compatibility patterns:
  - `app/domains/playback/top_movies_router.py`
  - `app/domains/playback/poster_router.py`
  - `app/domains/playback/chart_router.py`
