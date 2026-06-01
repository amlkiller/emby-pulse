# Migrate Proxy TMDB Helper

## Goal

Continue architecture phase 2 from `架构.md` by moving the proxy router TMDB JSON helper behind `tmdb_client`.

This batch should cover only the TMDB JSON requests in the proxy router. The router has since moved from `app/routers/proxy.py` to `app/domains/proxy/router.py`.

## Requirements

- Reuse `tmdb_client.search_multi()` for the proxy search step.
- Reuse `tmdb_client.get_tv_season()` for the season poster fallback step.
- Preserve existing behavior:
  - proxy support.
  - existing 5-second timeout.
  - Chinese language parameter.
  - image streaming/download remains outside `tmdb_client` and uses `image_proxy_client`.
  - search result order and poster fallback priority.
- Keep unrelated dirty files untouched.

## Acceptance Criteria

- [x] `app/domains/proxy/router.py` no longer hand-builds TMDB search or season URLs.
- [x] Image streaming remains outside `tmdb_client`; TMDB image bytes are fetched through `image_proxy_client`.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

Keep this as a transport extraction. Proxy routing and image streaming behavior stay local.

## Decision (ADR-lite)

**Context**: The proxy router still uses direct TMDB JSON URLs to select fallback images.

**Decision**: Move only the JSON fetches to `tmdb_client` and keep the image download session untouched.

**Consequences**: The proxy helper keeps its current streaming model while TMDB request construction is centralized.

## Out of Scope

- Do not move TMDB image byte downloads into `tmdb_client`.
- Do not change cached image URL behavior.
- Do not migrate unrelated proxy logic.

## Technical Notes

- Direct TMDB call sites were the `search/multi` lookup and the season fallback lookup in the image helper.
- Current implementation uses `tmdb_client.search_multi()` and `tmdb_client.get_tv_season()` from `app/domains/proxy/router.py`.
- Verification for this batch:
  - `uv run --with-requirements requirements.txt python -m compileall app/domains/proxy/router.py app/infra/clients/tmdb_client.py app/infra/clients/image_proxy_client.py` passed.
  - `uv run --with-requirements requirements.txt python -c "from app.infra.clients.tmdb_client import tmdb_client; import app.domains.proxy.router as proxy_router; assert hasattr(tmdb_client, 'search_multi'); assert hasattr(tmdb_client, 'get_tv_season'); assert proxy_router.image_proxy_client is not None; print('proxy tmdb helper checks ok')"` passed.
