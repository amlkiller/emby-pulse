# Migrate Media Request TMDB Calls

## Goal

Continue architecture phase 2 from `架构.md` by moving low-risk TMDB request-route calls behind the existing `tmdb_client` infrastructure boundary.

This batch should migrate the media request search/trending/TV-details transport without changing response shaping or request workflow behavior.

## Requirements

- Extend `app/infra/clients/tmdb_client.py` with helpers for:
  - multi search
  - trending with page support
  - TV details
- Migrate `app/routers/media_request.py` TMDB calls in:
  - `/api/requests/search`
  - `/api/requests/trending`
  - `/api/requests/tv/{tmdb_id}`
- Preserve existing route behavior:
  - proxy support.
  - 10-second timeouts.
  - Chinese language parameter.
  - response shaping remains in the route.
- Keep other TMDB calls in `media_request.py` out of scope for this batch.
- Keep unrelated dirty files untouched.

## Acceptance Criteria

- [x] `tmdb_client.search_multi()` exists and calls `/search/multi`.
- [x] `tmdb_client.get_trending()` supports `page`.
- [x] `tmdb_client.get_tv_details()` exists and calls `/tv/{tmdb_id}`.
- [x] The three selected `media_request.py` routes no longer hand-build TMDB URLs.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

Keep this as a transport extraction. Route-level auth, local Emby lookup, response shaping, and error handling stay in `media_request.py`.

## Decision (ADR-lite)

**Context**: `tmdb_client.py` exists but `media_request.py` still performs direct TMDB HTTP calls in core user-facing request flows.

**Decision**: Extend `tmdb_client` only enough to cover search, trending, and TV detail transport.

**Consequences**: More TMDB transport code is centralized while leaving the large media request workflow stable for later domain refactors.

## Out of Scope

- Do not migrate every TMDB call in `media_request.py`.
- Do not change local Emby lookups.
- Do not change response payloads, sorting, or cache behavior.

## Technical Notes

- Existing selected call sites are around `search_tmdb`, `get_tmdb_trending`, and `get_tv_details`.
- Other TMDB call sites in `media_request.py` should be migrated in later batches.
- Verification for this batch:
  - `uv run --with-requirements requirements.txt python -m compileall app/infra/clients/tmdb_client.py app/routers/media_request.py` passed.
  - `uv run --with-requirements requirements.txt python -c "from app.infra.clients.tmdb_client import tmdb_client; import app.routers.media_request; assert hasattr(tmdb_client, 'search_multi'); assert hasattr(tmdb_client, 'get_tv_details'); print('media request tmdb imports ok')"` passed.
  - `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v` passed with `68 passed, 4 warnings`.
