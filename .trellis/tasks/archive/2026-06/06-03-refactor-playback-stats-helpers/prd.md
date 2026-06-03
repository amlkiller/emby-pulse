# Refactor Playback Stats Helpers

## Goal

Reduce `app/domains/playback/stats.py` by extracting top-level stats helper functions into a domain-local helper module while preserving existing route behavior and compatibility imports.

## Requirements

- Add `app/domains/playback/stats_helpers.py` for the small cache helpers, auth helpers, media-name cleaning, poster-id resolution, admin user lookup, and user-name mapping currently defined near the top of `stats.py`.
- Import those helper names back into `stats.py` so existing tests, diagnostics, and monkeypatches that access `app.domains.playback.stats.<helper>` continue to work.
- Preserve the existing `_stats_cache` and `STATS_CACHE_TTL` behavior as module-level compatibility exports in `stats.py`.
- Do not change stats route URLs, response dict shapes, query SQL, permission behavior, dashboard cache service compatibility exports, or media client behavior.
- Keep playback stats public-auth boundary tests meaningful after the split.

## Acceptance Criteria

- [ ] `stats.py` no longer contains the helper function bodies for cache/auth/name/poster/user-map helpers.
- [ ] `stats_helpers.py` owns those helper implementations and imports only the dependencies needed for them.
- [ ] `app.domains.playback.stats` still exposes `get_cached_stats`, `set_cached_stats`, `check_login`, `require_admin_login`, `get_clean_name`, `resolve_poster_ids`, `get_admin_user_id`, and `get_user_map_local`.
- [ ] Existing focused playback stats tests pass.
- [ ] Full test suite passes before committing.

## Definition of Done

- Compile changed Python files with `uv run python -m compileall`.
- Run an import compatibility check through `uv run python -c`.
- Run focused playback stats public-auth and regression tests.
- Run the full test suite with `uv run pytest tests/ -v`.
- Commit the code/test slice, archive the Trellis task, and record the session journal.

## Technical Approach

Use the same compatibility-preserving pattern as prior DAO/router splits: move the helper implementations into a sibling module, import them back into the old large module, and update tests only where needed to keep boundary coverage across the new module.

## Out of Scope

- Moving stats route handlers into sub-routers.
- Changing dashboard cache service ownership or compatibility exports.
- Changing playback query construction, SQL filters, or API response schemas.
- Refactoring `playback/router.py` or `dashboard_cache_service.py`.

## Technical Notes

- Architecture audit target: `docs/架构审计.md` P2 item 5, small behavior-preserving splits of large domain files.
- Applicable specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`.
- Existing tests monkeypatch `stats.get_admin_user_id`, so compatibility exports must stay available from `stats.py`.
