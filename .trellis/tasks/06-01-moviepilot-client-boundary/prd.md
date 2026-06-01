# Refactor MoviePilot Client Boundary

## Goal

Continue architecture phase 2 from `架构.md` by moving direct MoviePilot HTTP access behind an infrastructure client boundary.

This batch should establish `app/infra/clients/moviepilot_client.py` and migrate the low-risk system connectivity test first.

## Requirements

- Create `app/infra/clients/moviepilot_client.py` as the MoviePilot client adapter.
- Export the new client from `app/infra/clients/__init__.py`.
- Preserve existing MoviePilot request behavior for the migrated route:
  - URL normalization with trailing slash removed.
  - token cleanup via stripping quotes.
  - `X-API-KEY` and `User-Agent` headers.
  - timeout and status-code behavior.
- Migrate `/api/settings/test_mp` in `app/routers/system.py` to the new client.
- Keep SSRF URL validation and route-level response messages in `app/routers/system.py`.
- Keep unrelated dirty files untouched.

## Acceptance Criteria

- [x] `app/infra/clients/moviepilot_client.py` exists and can call the MoviePilot site endpoint.
- [x] `app/infra/clients/__init__.py` exports the MoviePilot client.
- [x] `app/routers/system.py` uses the new MoviePilot client for `/api/settings/test_mp`.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

Use a conservative adapter extraction:

- Add a `MoviePilotClient` with helper methods for URL normalization, token cleanup, headers, and `test_site()`.
- Keep settings-route validation and user-facing messages unchanged.
- Do not migrate search or subscribe calls in this batch; those have broader domain behavior.

## Decision (ADR-lite)

**Context**: `架构.md` identifies MoviePilot as one of the external clients that should move under `app/infra/clients/`.

**Decision**: Introduce a small MoviePilot infrastructure client and migrate only the settings connectivity test first.

**Consequences**: The new boundary is available for future media request and gap-search migrations without changing user-facing behavior now.

## Out of Scope

- Do not migrate `/search_mp`, gap search, request approval, or bot-service MoviePilot subscribe logic yet.
- Do not redesign MoviePilot configuration access.
- Do not change route response structures or validation semantics.

## Technical Notes

- Existing direct call: `app/routers/system.py` uses `requests.get(f"{mp_url}/api/v1/site/", headers={"X-API-KEY": mp_token, "User-Agent": "Mozilla/5.0"}, timeout=8)`.
- Broader direct call sites include `app/routers/media_request.py`, `app/routers/gaps.py`, and `app/services/bot_service.py`.
- Previous external client batches created `media_server_client.py` and `tmdb_client.py`.
- Verification for this batch:
  - `uv run --with-requirements requirements.txt python -m compileall app/infra/clients app/routers/system.py` passed.
  - `uv run --with-requirements requirements.txt python -c "from app.infra.clients.moviepilot_client import MoviePilotClient, moviepilot_client; import app.routers.system; assert moviepilot_client.normalize_url(' https://x/ ') == 'https://x'; print('moviepilot imports ok')"` passed.
  - `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v` passed with `68 passed, 4 warnings`.
