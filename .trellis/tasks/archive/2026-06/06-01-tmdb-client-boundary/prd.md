# Refactor TMDB Client Boundary

## Goal

Start architecture phase 2 from `架构.md` by moving direct TMDB HTTP access behind an infrastructure client boundary.

This batch should establish `app/infra/clients/tmdb_client.py` as the shared TMDB adapter and migrate a couple of low-risk consumers to prove the boundary is usable.

## Requirements

- Create `app/infra/clients/tmdb_client.py` as the TMDB client adapter.
- Export the new client from `app/infra/clients/__init__.py`.
- Keep TMDB request behavior stable:
  - `api_key` query parameter handling.
  - proxy support.
  - timeouts and status-code handling used by existing routes.
- Migrate the TMDB connectivity test route in `app/routers/system.py` to the new client.
- Migrate the TMDB wallpaper lookup in `app/routers/views.py` to the new client.
- Keep unrelated dirty files untouched.

## Acceptance Criteria

- [x] `app/infra/clients/tmdb_client.py` exists and can fetch TMDB configuration and trending data.
- [x] `app/infra/clients/__init__.py` exports the TMDB client.
- [x] `app/routers/system.py` uses the new TMDB client for `/api/settings/test_tmdb`.
- [x] `app/routers/views.py` uses the new TMDB client for `/api/wallpaper`.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

Use a conservative adapter extraction:

- Add a small TMDB client with shared request construction and proxy-aware GET calls.
- Keep route-level error handling in place.
- Migrate only the direct TMDB call sites that are easy to verify first.
- Leave broader TMDB consumers in services/plugins for later batches.

## Decision (ADR-lite)

**Context**: `架构.md` names external clients as the next architectural boundary after the database refactor. TMDB calls are currently repeated directly in routers, services, and plugins.

**Decision**: Introduce a shared TMDB infrastructure client and migrate the safest route consumers first.

**Consequences**: This removes one more direct external dependency from `app/routers/` without a wide behavior sweep. Later batches can reuse the same client from services and plugins.

## Out of Scope

- Do not migrate every TMDB call site in the repository yet.
- Do not introduce Telegram, WeCom, or MoviePilot clients in this task.
- Do not redesign configuration access.
- Do not change any TMDB endpoint semantics beyond centralizing the request code.

## Technical Notes

- Existing TMDB direct call sites include `app/routers/system.py`, `app/routers/views.py`, `app/services/report_service.py`, `app/services/calendar_service.py`, `app/services/user_bot_service.py`, and `app/plugins/hdhive/plugin.py`.
- TMDB requests currently use `requests.get(...)` with `cfg.get("tmdb_api_key")` and occasional proxy lookup via `app.utils.proxy_helper.get_safe_proxies()`.
- Current tests for the previous batch passed with `68 passed, 4 warnings`.
- Verification for this batch:
  - `uv run --with-requirements requirements.txt python -m compileall app/infra/clients app/routers/system.py app/routers/views.py` passed.
  - `uv run --with-requirements requirements.txt python -c "from app.infra.clients.tmdb_client import TmdbClient, tmdb_client; import app.routers.system; assert tmdb_client.base_url.endswith('/3'); print('tmdb client imports ok')"` passed.
  - `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v` passed with `68 passed, 4 warnings`.
- Importing `app.routers.views` directly still hits the repository's existing route-import cycle through `app.main` / `app.bootstrap.routes` / `app.routers.calendar`; this was not introduced by the TMDB client extraction and should be handled in a separate routing cleanup.
