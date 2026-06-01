# Migrate Bot TMDB Poster Fallback

## Goal

Continue architecture phase 2 from `架构.md` by moving the bot service TMDB poster fallback in `app/services/bot_service.py` behind `tmdb_client`.

This batch should cover only the delete-notification TMDB poster lookup.

## Requirements

- Reuse `tmdb_client.get_movie_details()` and `tmdb_client.get_tv_details()` for poster fallback.
- Preserve existing behavior:
  - proxy support.
  - existing 5-second timeout.
  - movie-first lookup, TV fallback for poster lookup.
  - poster URL composition and message formatting.
- Keep unrelated dirty files untouched.

## Acceptance Criteria

- [x] TMDB poster fallback no longer hand-builds TMDB detail URLs.
- [x] Movie-first / TV-fallback lookup order is preserved.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

Keep this as a transport extraction. Notification content, media selection priority, and send behavior stay in `bot_service.py`.

## Decision (ADR-lite)

**Context**: The bot service still constructs TMDB detail URLs directly when it needs a poster image and no local media image exists.

**Decision**: Move only the TMDB transport into `tmdb_client`, keeping the notification fallback logic unchanged.

**Consequences**: Bot notification flows use the shared TMDB client boundary without changing how a poster is chosen.

## Out of Scope

- Do not migrate Telegram send logic.
- Do not change Emby image download behavior.
- Do not change the fallback poster priority.

## Technical Notes

- Direct TMDB call site is in the delete notification branch around `tmdb_img_url`.
- Verification for this batch:
  - `uv run --with-requirements requirements.txt python -m compileall app/services/bot_service.py app/infra/clients/tmdb_client.py` passed.
  - `uv run --with-requirements requirements.txt python -c "from app.infra.clients.tmdb_client import tmdb_client; import app.services.bot_service; assert hasattr(tmdb_client, 'get_movie_details'); assert hasattr(tmdb_client, 'get_tv_details'); print('bot tmdb poster checks ok')"` passed.
  - `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v` passed with `68 passed, 4 warnings`.
