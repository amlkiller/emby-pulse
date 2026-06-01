# Migrate Report TMDB Poster Search

## Goal

Continue architecture phase 2 from `架构.md` by moving report poster fallback TMDB search calls behind `tmdb_client`.

This batch should cover only `_fetch_tmdb_poster()` in `app/services/report_service.py`.

## Requirements

- Reuse `tmdb_client.search_movie()` and `tmdb_client.search_tv()` for poster fallback search.
- Preserve existing behavior:
  - return `None` when TMDB is not configured.
  - proxy support.
  - existing 5-second TMDB search timeout.
  - TV search when `is_tv=True`.
  - movie search first, then TV fallback when `is_tv=False`.
  - image download and resizing remain unchanged.
- Keep unrelated dirty files untouched.

## Acceptance Criteria

- [x] `_fetch_tmdb_poster()` no longer hand-builds TMDB search URLs.
- [x] Movie-first / TV-fallback search order is preserved.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

Keep this as a transport extraction. PIL image decoding, resizing, and final image URL download remain in `report_service.py`.

## Decision (ADR-lite)

**Context**: Report poster fallback still constructs TMDB search URLs directly even though `tmdb_client` now has endpoint-specific search helpers.

**Decision**: Use the shared search helpers and keep image processing local to the report service.

**Consequences**: TMDB search transport continues moving into the infrastructure boundary while report rendering stays unchanged.

## Out of Scope

- Do not change report layout or poster image processing.
- Do not centralize TMDB image URL construction in this batch.
- Do not migrate unrelated report queries.

## Technical Notes

- Direct TMDB call sites are in `_fetch_tmdb_poster()`.
- Verification for this batch:
  - `uv run --with-requirements requirements.txt python -m compileall app/services/report_service.py app/infra/clients/tmdb_client.py` passed.
  - `uv run --with-requirements requirements.txt python -c "from app.infra.clients.tmdb_client import tmdb_client; import app.services.report_service; assert hasattr(tmdb_client, 'search_movie'); assert hasattr(tmdb_client, 'search_tv'); print('report tmdb poster checks ok')"` passed.
  - `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v` passed with `68 passed, 4 warnings`.
