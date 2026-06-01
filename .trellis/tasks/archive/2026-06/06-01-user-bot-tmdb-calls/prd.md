# Migrate User Bot TMDB Calls

## Goal

Continue architecture phase 2 from `架构.md` by moving user Telegram bot TMDB search and detail calls behind `tmdb_client`.

This batch should cover only `app/services/user_bot_service.py` TMDB transport used by the `/request` workflow.

## Requirements

- Reuse `tmdb_client.search_multi()` for `/request` search.
- Reuse `tmdb_client.get_tv_details()` for TV season selection.
- Add and reuse `tmdb_client.get_movie_details()` for movie detail fetches.
- Preserve existing behavior:
  - "TMDB not configured" user-facing error.
  - proxy support.
  - existing 10-second timeouts.
  - Chinese language parameter.
  - result filtering and top-5 selection.
  - request submission data shape.
- Keep unrelated dirty files untouched.

## Acceptance Criteria

- [x] `/request` search no longer hand-builds TMDB search URLs.
- [x] TV season selection no longer hand-builds TMDB TV detail URLs.
- [x] Request submission no longer hand-builds TMDB movie/TV detail URLs.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

Keep this as a transport extraction. Telegram message formatting, callback payloads, local binding checks, and DAO submission stay in the bot service.

## Decision (ADR-lite)

**Context**: `tmdb_client` already handles multi-search and TV details. User bot still directly constructs TMDB URLs.

**Decision**: Add only the missing movie detail helper and migrate the three `/request` workflow TMDB fetches.

**Consequences**: User bot request workflow uses the shared client boundary without changing user-facing bot behavior.

## Out of Scope

- Do not migrate Telegram API transport.
- Do not change request approval or DAO behavior.
- Do not migrate other services or plugins in this batch.

## Technical Notes

- Direct TMDB call sites are in `cmd_request()`, `cmd_request_callback()`, and `_submit_request()`.
- Verification for this batch:
  - `uv run --with-requirements requirements.txt python -m compileall app/services/user_bot_service.py app/infra/clients/tmdb_client.py` passed.
  - `uv run --with-requirements requirements.txt python -c "from app.infra.clients.tmdb_client import tmdb_client; import app.services.user_bot_service; assert hasattr(tmdb_client, 'search_multi'); assert hasattr(tmdb_client, 'get_movie_details'); print('user bot tmdb checks ok')"` passed.
  - `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v` passed with `68 passed, 4 warnings`.
