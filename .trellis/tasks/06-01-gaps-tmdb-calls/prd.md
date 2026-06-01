# Migrate Gaps TMDB Calls

## Goal

Continue architecture phase 2 from `架构.md` by moving the low-risk TMDB calls in `app/routers/gaps.py` behind `tmdb_client`.

This batch should cover gap scanning TV detail/season calls and the fallback HDHive TMDB keyword search calls.

## Requirements

- Reuse `tmdb_client.get_tv_details()` for gap scan series metadata.
- Reuse `tmdb_client.get_tv_season()` for gap scan season episode metadata.
- Add narrow TMDB client helpers for movie search and TV search if needed to preserve endpoint-specific search behavior.
- Migrate `search_mp_for_gap()` fallback TMDB search calls without changing HDHive lookup behavior.
- Preserve existing behavior:
  - proxy support.
  - existing timeouts.
  - Chinese language parameter.
  - response parsing and fallback order.
- Keep unrelated dirty files untouched.

## Acceptance Criteria

- [x] `process_single_series()` no longer hand-builds TMDB TV detail or season URLs.
- [x] `search_mp_for_gap()` no longer hand-builds TMDB search URLs.
- [x] Endpoint-specific movie/TV search behavior is preserved.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

Keep this as a transport extraction. Gap inventory comparison, locking, HDHive plugin calls, and response shaping stay in `app/routers/gaps.py`.

## Decision (ADR-lite)

**Context**: `tmdb_client` already owns TMDB request construction and has helpers for TV details and season details. `gaps.py` still manually constructs TMDB URLs.

**Decision**: Move only the TMDB transport into `tmdb_client`, adding endpoint-specific search helpers rather than changing fallback search semantics.

**Consequences**: Gap scanning and fallback search use the shared TMDB infrastructure boundary without changing gap detection logic.

## Out of Scope

- Do not migrate MoviePilot or HDHive plugin transport.
- Do not change gap detection, cache, or lock semantics.
- Do not alter response payloads.

## Technical Notes

- Direct TMDB call sites are in `process_single_series()` and the fallback TMDB keyword search path inside `search_mp_for_gap()`.
- Verification for this batch:
  - `uv run --with-requirements requirements.txt python -m compileall app/infra/clients/tmdb_client.py app/routers/gaps.py` passed.
  - `uv run --with-requirements requirements.txt python -c "from app.infra.clients.tmdb_client import tmdb_client; import app.routers.gaps; assert hasattr(tmdb_client, 'search_movie'); assert hasattr(tmdb_client, 'search_tv'); print('gaps tmdb checks ok')"` passed.
  - `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v` passed with `68 passed, 4 warnings`.
