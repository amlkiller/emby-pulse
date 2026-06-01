# Migrate Proxy TMDB Helper

## Goal

Continue architecture phase 2 from `架构.md` by moving the proxy router TMDB JSON helper behind `tmdb_client`.

This batch should cover only the TMDB JSON requests in `app/routers/proxy.py`.

## Requirements

- Reuse `tmdb_client.search_multi()` for the proxy search step.
- Reuse `tmdb_client.get_tv_season()` for the season poster fallback step.
- Preserve existing behavior:
  - proxy support.
  - existing 5-second timeout.
  - Chinese language parameter.
  - ext_session remains responsible for image streaming/download.
  - search result order and poster fallback priority.
- Keep unrelated dirty files untouched.

## Acceptance Criteria

- [ ] `app/routers/proxy.py` no longer hand-builds TMDB search or season URLs.
- [ ] `ext_session` remains in use for image streaming.
- [ ] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [ ] Existing tests still pass.

## Technical Approach

Keep this as a transport extraction. Proxy routing and image streaming behavior stay local.

## Decision (ADR-lite)

**Context**: The proxy router still uses direct TMDB JSON URLs to select fallback images.

**Decision**: Move only the JSON fetches to `tmdb_client` and keep the image download session untouched.

**Consequences**: The proxy helper keeps its current streaming model while TMDB request construction is centralized.

## Out of Scope

- Do not remove the custom `ext_session`.
- Do not change cached image URL behavior.
- Do not migrate unrelated proxy logic.

## Technical Notes

- Direct TMDB call sites are the `search/multi` lookup and the season fallback lookup in the image helper.
