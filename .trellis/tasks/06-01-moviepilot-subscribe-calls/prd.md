# Migrate MoviePilot Subscribe Calls

## Goal

Continue architecture phase 2 from `架构.md` by moving low-risk MoviePilot subscribe POST calls behind the existing `moviepilot_client` infrastructure boundary.

This batch should migrate subscription creation calls while preserving request approval behavior.

## Requirements

- Extend `app/infra/clients/moviepilot_client.py` with a `subscribe()` helper.
- Preserve existing MoviePilot subscribe behavior:
  - URL normalization with trailing slash removed.
  - token cleanup via stripping quotes.
  - `X-API-KEY` header.
  - 10-second timeout at existing call sites.
  - callers may ignore failures exactly as before.
- Migrate MoviePilot subscribe POST in `app/routers/media_request.py`.
- Migrate MoviePilot subscribe POST in `app/services/bot_service.py`.
- Keep gap search and other MoviePilot GET calls out of scope for this batch.
- Keep unrelated dirty files untouched.

## Acceptance Criteria

- [x] `moviepilot_client.subscribe()` exists and posts to `/api/v1/subscribe/`.
- [x] `app/routers/media_request.py` no longer directly posts to MoviePilot subscribe.
- [x] `app/services/bot_service.py` no longer directly posts to MoviePilot subscribe.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

Add a thin infrastructure helper and keep the caller-owned payload assembly in place. This avoids changing media request approval semantics while removing duplicated transport/header/URL logic.

## Decision (ADR-lite)

**Context**: `moviepilot_client.py` already owns MoviePilot connectivity testing. Subscribe calls still duplicate endpoint construction and header/token cleanup in router/service code.

**Decision**: Add `subscribe()` to the client and migrate only the low-risk POST call sites that already swallow failures.

**Consequences**: MoviePilot subscription transport is centralized. Search-related MoviePilot logic can move later without coupling this task to gap matching behavior.

## Out of Scope

- Do not migrate `/search_mp` or gap search calls.
- Do not alter approval status updates, notification behavior, or payload shape.
- Do not introduce retries or new logging.

## Technical Notes

- Direct subscribe call sites:
  - `app/routers/media_request.py`
  - `app/services/bot_service.py`
- Previous MoviePilot batch introduced `app/infra/clients/moviepilot_client.py`.
- Verification for this batch:
  - `uv run --with-requirements requirements.txt python -m compileall app/infra/clients/moviepilot_client.py app/routers/media_request.py app/services/bot_service.py` passed.
  - `uv run --with-requirements requirements.txt python -c "from app.infra.clients.moviepilot_client import moviepilot_client; import app.routers.media_request; import app.services.bot_service; assert hasattr(moviepilot_client, 'subscribe'); print('moviepilot subscribe imports ok')"` passed.
  - `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v` passed with `68 passed, 4 warnings`.
