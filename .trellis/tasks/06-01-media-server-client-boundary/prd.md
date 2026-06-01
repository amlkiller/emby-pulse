# Refactor Media Server Client Boundary

## Goal

Start architecture phase 2 from `架构.md` by moving the existing Emby/Jellyfin media server adapter behind an infrastructure client boundary.

This batch should establish `app/infra/clients/` as the home for external client adapters without changing media server behavior or sweeping every consumer at once.

## Requirements

- Create `app/infra/clients/` as the external client adapter package.
- Move the existing `MediaServerAdapter` implementation and `media_api` singleton from `app/core/media_adapter.py` into `app/infra/clients/media_server_client.py`.
- Keep `app/core/media_adapter.py` as a temporary compatibility shell that re-exports the new infrastructure client, because many routers, services, and plugins still import it.
- Migrate one small, low-risk consumer from `app.core.media_adapter` to the new `app.infra.clients.media_server_client` import to prove the new boundary is usable.
- Preserve existing request behavior:
  - Emby/Jellyfin path normalization.
  - Auth header behavior.
  - `api_key` query parameter injection.
  - multipart upload content-type handling.
  - session retry/pool behavior.
  - `health_check()` caching and timeout behavior.
- Keep unrelated dirty files untouched.

## Acceptance Criteria

- [x] `app/infra/clients/media_server_client.py` exists and owns `MediaServerAdapter` plus `media_api`.
- [x] `app/core/media_adapter.py` contains only a temporary compatibility re-export, not the implementation.
- [x] At least one application consumer imports `media_api` from `app.infra.clients.media_server_client`.
- [x] Existing imports from `app.core.media_adapter` still work during the transition.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

Use a conservative move-first refactor:

- Introduce `app/infra/clients/__init__.py`.
- Copy the current adapter implementation into `app/infra/clients/media_server_client.py`.
- Replace `app/core/media_adapter.py` with a thin compatibility shell.
- Change one small consumer import to the new infra path.
- Run compile/import checks and the existing pytest suite.

## Decision (ADR-lite)

**Context**: `架构.md` identifies external clients as phase 2 after database boundary cleanup. The current media server adapter is already a reusable client abstraction, but it lives under `app/core/`, while the target architecture places external adapters under `app/infra/clients/`.

**Decision**: Move the adapter implementation first and keep a temporary compatibility shell for existing consumers.

**Consequences**: This establishes the new boundary with low blast radius. Remaining consumers can migrate incrementally in later batches, and the compatibility shell should be removed once no imports remain.

## Out of Scope

- Do not migrate all Emby/Jellyfin direct `requests.*` usage in this task.
- Do not introduce TMDB, Telegram, WeCom, or MoviePilot clients in this task.
- Do not redesign configuration access.
- Do not change API routes, response structures, retry policy, or media server behavior.
- Do not delete the compatibility shell in `app/core/media_adapter.py` yet.

## Technical Notes

- `架构.md` phase 2 target: `app/infra/clients/emby_client.py`, `tmdb_client.py`, `telegram_client.py`, `wecom_client.py`, `moviepilot_client.py`.
- Existing adapter: `app/core/media_adapter.py`.
- Existing consumers include routers, services, and plugins. A full import migration should be a later batch after the boundary is established.
- Current tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v` recently passed with `68 passed, 4 warnings`.
