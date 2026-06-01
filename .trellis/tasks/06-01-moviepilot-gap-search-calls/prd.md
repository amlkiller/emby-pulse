# Migrate MoviePilot Gap Search Calls

## Goal

Continue architecture phase 2 from `架构.md` by moving MoviePilot gap-search GET calls behind the existing `moviepilot_client` infrastructure boundary.

This batch should migrate only the transport for `/api/v1/search/title` calls in `app/routers/gaps.py` while preserving the gap matching and scoring behavior.

## Requirements

- Extend `app/infra/clients/moviepilot_client.py` with a `search_title()` helper.
- Preserve existing MoviePilot search behavior:
  - URL normalization with trailing slash removed.
  - token cleanup via stripping quotes.
  - `X-API-KEY`, `User-Agent`, and `Accept` headers.
  - keyword query passed as `keyword`.
  - 20-second timeout at existing call sites.
  - JSON shape handling remains in `app/routers/gaps.py`.
- Migrate the single-episode search call in `app/routers/gaps.py`.
- Migrate the full-season fallback search call in `app/routers/gaps.py`.
- Keep matching/scoring/business logic untouched.
- Keep unrelated dirty files untouched.

## Acceptance Criteria

- [x] `moviepilot_client.search_title()` exists and calls `/api/v1/search/title`.
- [x] `app/routers/gaps.py` no longer builds MoviePilot search URLs directly for `/api/v1/search/title`.
- [x] Existing gap result parsing and scoring logic remains in `app/routers/gaps.py`.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

Add a thin search helper to `moviepilot_client` and leave response parsing at the call site. This keeps the transport concern in infrastructure while avoiding a behavior change in gap matching.

## Decision (ADR-lite)

**Context**: MoviePilot connectivity and subscribe calls already use `moviepilot_client`; gap search still duplicates headers, URL construction, and token cleanup.

**Decision**: Centralize only the MoviePilot search transport in `moviepilot_client.search_title()` while leaving domain-specific result interpretation in `gaps.py`.

**Consequences**: MoviePilot request construction becomes centralized without coupling the infrastructure client to gap-scoring rules.

## Out of Scope

- Do not alter gap search result ranking/scoring.
- Do not migrate non-MoviePilot gap logic.
- Do not add retries, caching, or logging.

## Technical Notes

- Existing direct calls are in `app/routers/gaps.py` around the `search_mp_for_gap()` flow.
- Previous MoviePilot batches introduced `test_site()` and `subscribe()` on `app/infra/clients/moviepilot_client.py`.
- Verification for this batch:
  - `uv run --with-requirements requirements.txt python -m compileall app/infra/clients/moviepilot_client.py app/routers/gaps.py` passed.
  - `uv run --with-requirements requirements.txt python -c "from app.infra.clients.moviepilot_client import moviepilot_client; import app.routers.gaps; assert hasattr(moviepilot_client, 'search_title'); print('moviepilot search imports ok')"` passed.
  - `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v` passed with `68 passed, 4 warnings`.
