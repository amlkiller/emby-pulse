# Refactor Playback Stats Live Router

## Goal

Continue the P2 architecture audit work by extracting the live playback session endpoints from `app/domains/playback/stats.py` into a focused playback-domain child router, reducing mixed responsibilities while preserving behavior.

## Requirements

- Extract `GET /api/stats/live` and legacy `GET /api/live` into a new playback child router module.
- Include the child router from `app/domains/playback/stats.py` at the original route position, after `/api/stats/latest` and before `/api/stats/top_movies`.
- Preserve compatibility exports from `app.domains.playback.stats` for:
  - `api_live_sessions`
  - `api_live_sessions_legacy`
- Preserve monkeypatch behavior by resolving old `stats` module globals at call time through provider callables for:
  - `user_service`
  - `media_api`
- Keep route URLs, request parameters, response shapes, admin permission checks, media server calls, timeout behavior, and exception fallback behavior unchanged.
- Add or update focused boundary tests for child router inclusion, compatibility exports, route ordering, and old-module monkeypatch behavior.

## Acceptance Criteria

- `app/domains/playback/stats.py` is smaller and delegates both live routes to a new child router module.
- `/api/stats/live` and `/api/live` remain present under `stats.router`.
- `app.domains.playback.stats.api_live_sessions` and `api_live_sessions_legacy` remain the same function objects as the new child router exports.
- The route order remains `/api/stats/latest` -> `/api/stats/live` -> `/api/live` -> `/api/stats/top_movies`.
- Existing tests that monkeypatch `stats.user_service.is_admin_user` or `stats.media_api.get` still pass.
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

Follow the existing playback child-router/provider pattern used by `libraries_router.py` and `latest_router.py`. The new module should own the moved route handlers and dependency providers. `stats.py` should import the handlers for compatibility, configure providers with lambdas that resolve current `stats` globals at request time, and include the child router exactly where the original route handlers were declared.

## Out of Scope

- Do not refactor ranking endpoints, user details, chart/trend, poster data, badges, dashboard cache endpoints, system monitor, item detail, DAO/query logic, or lifecycle behavior in this slice.
- Do not change media server transport behavior.
- Do not add new response fields or error shapes.
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
