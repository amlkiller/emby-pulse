# Migrate Media Request TMDB Season Calls

## Goal

Continue architecture phase 2 from `架构.md` by moving TMDB TV season detail calls in `app/routers/media_request.py` behind `tmdb_client`.

This batch should migrate the repeated `/tv/{tmdb_id}/season/{season}` transport only.

## Requirements

- Add `tmdb_client.get_tv_season(tmdb_id, season, ...)`.
- Migrate `get_tmdb_season_info()` to use `tmdb_client.get_tv_season()`.
- Migrate `_get_tmdb_season_episodes()` to use `tmdb_client.get_tv_season()`.
- Preserve existing behavior:
  - proxy support.
  - existing timeouts at each call site.
  - Chinese language parameter.
  - route/helper parsing logic remains unchanged.
- Keep unrelated dirty files untouched.

## Acceptance Criteria

- [x] `tmdb_client.get_tv_season()` exists and calls `/tv/{tmdb_id}/season/{season}`.
- [x] `get_tmdb_season_info()` no longer hand-builds a TMDB season URL.
- [x] `_get_tmdb_season_episodes()` no longer hand-builds a TMDB season URL.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

Extract only the TMDB transport. Keep unaired episode calculation and chase-update episode shaping in the existing helper functions.

## Decision (ADR-lite)

**Context**: The previous media-request TMDB batch migrated search, trending, and TV detail calls. Season detail calls remain as repeated direct URL construction.

**Decision**: Add a dedicated `get_tv_season()` client helper and migrate both helper functions that need season details.

**Consequences**: TMDB season transport is centralized while preserving request workflow behavior.

## Out of Scope

- Do not migrate all remaining TMDB calls in `media_request.py`.
- Do not alter notification or chase-update workflows.
- Do not change response shapes.

## Technical Notes

- Direct season detail call sites are in `get_tmdb_season_info()` and `_get_tmdb_season_episodes()`.
- Verification for this batch:
  - `uv run --with-requirements requirements.txt python -m compileall app/infra/clients/tmdb_client.py app/routers/media_request.py` passed.
  - `uv run --with-requirements requirements.txt python -c "from app.infra.clients.tmdb_client import tmdb_client; import app.routers.media_request; assert hasattr(tmdb_client, 'get_tv_season'); print('media request tmdb season imports ok')"` passed.
  - `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v` passed with `68 passed, 4 warnings`.
