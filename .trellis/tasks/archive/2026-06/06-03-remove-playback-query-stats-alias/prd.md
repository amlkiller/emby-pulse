# Remove playback query_stats alias

## Goal

Remove `app.domains.playback.stats_queries.query_stats`, a pure forwarding wrapper around `app.infra.db.playback_store.playback_store.query`.

## Scope

- Replace internal playback statistics calls with `playback_store.query(...)`.
- Replace notification bot report calls with `playback_store.query(...)`.
- Update tests that monkeypatch the old alias to monkeypatch the real query boundary.
- Delete only `query_stats` from `stats_queries.py`.

## Non-Goals

- Do not remove `build_stats_base_filter`, `get_user_last_play`, or `get_user_play_summary`; they encode domain query/filter semantics.
- Do not change SQL strings, query parameters, cache behavior, authorization flow, or result handling.
- Do not alter playback store implementation.

## Acceptance

- `query_stats` is no longer defined or imported from `stats_queries.py`.
- Runtime callers use `playback_store.query(...)` directly.
- Focused compile/import checks pass.
- Full `uv run pytest tests/ -v` passes with UTF-8 output on Windows.
