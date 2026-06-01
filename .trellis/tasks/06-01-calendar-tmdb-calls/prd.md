# Migrate Calendar TMDB Calls

## Goal

Continue architecture phase 2 from `架构.md` by moving the weekly calendar TMDB TV detail and season calls behind `tmdb_client`.

This batch should cover only `app/services/calendar_service.py` TMDB transport.

## Requirements

- Reuse `tmdb_client.get_tv_details()` for series metadata in `_fetch_series_status()`.
- Reuse `tmdb_client.get_tv_season()` for season episode metadata in `_fetch_series_status()`.
- Preserve existing behavior:
  - proxy support.
  - existing 5-second timeouts.
  - Chinese language parameter.
  - status-code checks before parsing.
  - weekly episode filtering and Emby file checks.
- Keep unrelated dirty files untouched.

## Acceptance Criteria

- [x] `_fetch_series_status()` no longer hand-builds TMDB TV detail or season URLs.
- [x] Existing status-code based early returns are preserved.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

Keep this as a transport extraction. Calendar cache, ended-series persistence, weekly date filtering, and Emby inventory checks remain in the service.

## Decision (ADR-lite)

**Context**: `tmdb_client` already centralizes TMDB TV detail and season calls. Calendar service still manually constructs those URLs.

**Decision**: Migrate only the two direct calendar TMDB fetches to the shared client.

**Consequences**: Calendar service keeps its workflow while TMDB transport continues moving into the infrastructure boundary.

## Out of Scope

- Do not change calendar cache semantics.
- Do not change ended-series status persistence.
- Do not migrate unrelated Emby requests.

## Technical Notes

- Direct TMDB call sites are in `_fetch_series_status()`.
- Verification for this batch:
  - `uv run --with-requirements requirements.txt python -m compileall app/services/calendar_service.py app/infra/clients/tmdb_client.py` passed.
  - `uv run --with-requirements requirements.txt python -c "from app.infra.clients.tmdb_client import tmdb_client; import app.services.calendar_service; assert hasattr(tmdb_client, 'get_tv_details'); assert hasattr(tmdb_client, 'get_tv_season'); print('calendar tmdb checks ok')"` passed.
  - `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v` passed with `68 passed, 4 warnings`.
