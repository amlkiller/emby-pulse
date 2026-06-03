# Refactor Playback Stats Latest Router

## Goal

Continue the P2 architecture audit work by extracting the `GET /api/stats/latest` endpoint from `app/domains/playback/stats.py` into a focused playback-domain child router, reducing mixed responsibilities while preserving behavior.

## Requirements

- Extract `GET /api/stats/latest` and its local TMDB/latest-media assembly logic into a new playback child router module.
- Include the child router from `app/domains/playback/stats.py` at the original route position, after `/api/stats/recent` and before `/api/stats/live`.
- Preserve `app.domains.playback.stats.api_latest_media` as a compatibility export for existing internal callers and tests.
- Preserve monkeypatch behavior by resolving old `stats` module globals at call time through provider callables for:
  - `check_login`
  - `get_admin_user_id`
  - `media_api`
  - `tmdb_client`
  - `get_safe_proxies`
- Keep route URLs, request parameters, response shapes, timeouts, concurrency behavior, and exception fallback behavior unchanged.
- Add or update focused boundary tests for child router inclusion, compatibility export, and route ordering.

## Acceptance Criteria

- `app/domains/playback/stats.py` is smaller and delegates `/api/stats/latest` to a new child router module.
- `/api/stats/latest` remains present under `stats.router`.
- `app.domains.playback.stats.api_latest_media` remains the same function object as the new child router export.
- The route order remains `/api/stats/recent` -> `/api/stats/latest` -> `/api/stats/live`.
- Existing tests that monkeypatch `stats` module globals still pass.
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

Follow the existing `app/domains/playback/libraries_router.py` child-router/provider pattern. The new module should own the moved route handler and dependency providers. `stats.py` should import the handler for compatibility, configure providers with lambdas that resolve current `stats` globals at request time, and include the child router exactly where the original route was declared.

## Out of Scope

- Do not refactor `/api/stats/recent`, `/api/stats/live`, ranking endpoints, dashboard cache endpoints, system monitor, item detail, DAO/query logic, or lifecycle behavior in this slice.
- Do not change media server or TMDB transport behavior.
- Do not add new response fields or error shapes.
- Do not change database schema or external client adapters.

## Technical Notes

- Relevant audit item: `docs/架构审计.md` P2 issue 5, large mixed-responsibility domain files.
- Relevant specs:
  - `.trellis/spec/backend/directory-structure.md`
  - `.trellis/spec/backend/quality-guidelines.md`
  - `.trellis/spec/backend/error-handling.md`
- Existing compatibility pattern: `app/domains/playback/libraries_router.py`.
