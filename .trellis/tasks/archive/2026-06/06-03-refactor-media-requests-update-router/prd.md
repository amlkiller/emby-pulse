# Refactor Media Requests Update Router

## Goal

Continue the P2 architecture audit work by extracting the media request "追新" update endpoints from `app/domains/media_requests/router.py` into a focused domain-local child router module.

## Scope

- Extract the following endpoints into a new child router module:
  - `POST /api/user/request_update`
  - `POST /api/user/request_update_batch`
  - `POST /api/manage/requests/search_episodes`
  - `POST /api/manage/requests/download_episodes`
- Move `UpdateRequestModel` and `getRequestStatusTextSync` with that route group.
- Include the new child router from `media_requests/router.py` at the original route position.
- Preserve compatibility exports from `app.domains.media_requests.router` for moved models, helpers, and route handlers.
- Preserve existing test monkeypatch behavior by resolving old `media_requests.router` globals through provider callables at request time.

## Non-Goals

- Do not change route paths, methods, auth checks, request parsing, response payloads, notification behavior, database writes, MoviePilot/TMDB/media server interactions, or safe error mapping.
- Do not refactor the remaining new media request submit endpoint in this slice.
- Do not change database schema or external client transport behavior.
- Do not deepen cross-domain imports beyond the dependencies already used by the existing route code.

## Acceptance Criteria

- `app/domains/media_requests/router.py` is smaller and delegates the update endpoints to a new child router module.
- The four update endpoints remain present under the main `media_requests.router.router`.
- Compatibility imports from `app.domains.media_requests.router` continue to expose moved functions/models.
- Existing route ordering around the moved endpoints is preserved.
- Verification passes:
  - `uv run python -m compileall` for changed Python files.
  - An import/route compatibility check through `uv run python -c ...` with UTF-8 output on Windows if needed.
  - Focused media request router boundary tests.
  - Full `uv run pytest tests/ -v`.
