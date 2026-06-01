# Migrate Stats TMDB Poster Fetch

## Goal

Continue architecture phase 2 from `架构.md` by moving the stats router TMDB poster/overview fetch behind `tmdb_client`.

This batch should cover only the TMDB detail fetch in `app/routers/stats.py`.

## Requirements

- Reuse `tmdb_client.get_movie_details()` and `tmdb_client.get_tv_details()` for stats poster/overview lookup.
- Preserve existing behavior:
  - proxy support.
  - existing 8-second timeout.
  - Chinese language parameter.
  - status-code check before parsing.
  - concurrent fanout and local response shaping.
- Keep unrelated dirty files untouched.

## Acceptance Criteria

- [x] `app/routers/stats.py` no longer hand-builds TMDB detail URLs.
- [x] Existing poster/overview response shaping is preserved.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

Keep this as a transport extraction. The stats router keeps local Emby data handling, concurrent fetch orchestration, and poster URL shaping.

## Decision (ADR-lite)

**Context**: `stats.py` still directly constructs TMDB movie/TV detail URLs while `tmdb_client` already has endpoint-specific detail helpers.

**Decision**: Replace the direct URL construction with the shared TMDB client helpers only.

**Consequences**: The stats router loses direct TMDB transport code without changing its UI-facing data shape.

## Out of Scope

- Do not change stats ranking or item aggregation.
- Do not centralize TMDB image URL composition in this batch.
- Do not migrate unrelated Emby requests.

## Technical Notes

- Direct TMDB call site is the local `fetch_tmdb()` helper inside the recent items flow.
- Verification for this batch:
  - `uv run --with-requirements requirements.txt python -m compileall app/routers/stats.py app/infra/clients/tmdb_client.py` passed.
  - `uv run --with-requirements requirements.txt python -c "from app.infra.clients.tmdb_client import tmdb_client; import app.routers.stats; assert hasattr(tmdb_client, 'get_movie_details'); assert hasattr(tmdb_client, 'get_tv_details'); print('stats tmdb checks ok')"` passed.
  - `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v` passed with `68 passed, 4 warnings`.
