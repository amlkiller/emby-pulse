# Refactor Media Requests Submit Router

## Goal

Continue the P2 architecture audit work by extracting the remaining new media request submit endpoint from `app/domains/media_requests/router.py` into a focused domain-local child router module.

## Scope

- Extract `POST /api/requests/submit` into a new child router module.
- Move `MediaRequestSubmitModel` with the submit route group.
- Include the child router from `media_requests/router.py` at the original route position between discovery and management routes.
- Preserve compatibility exports from `app.domains.media_requests.router` for the moved model and route handler.
- Preserve existing monkeypatch behavior by resolving old `media_requests.router` globals through provider callables at request time.

## Non-Goals

- Do not change route path, method, auth checks, request parsing, response payloads, notification rule behavior, database writes, plugin checks, or safe error mapping.
- Do not refactor community cache lifecycle helpers, discovery, management, feedback, safe media, user series, update, registration, gaps, or DAO behavior in this slice.
- Do not change database schema or external client transport behavior.
- Do not introduce new cross-domain dependencies beyond the dependencies already used by the existing route code.

## Acceptance Criteria

- `app/domains/media_requests/router.py` is smaller and delegates the submit endpoint to a new child router module.
- `POST /api/requests/submit` remains present under the main `media_requests.router.router`.
- Compatibility imports from `app.domains.media_requests.router` continue to expose `MediaRequestSubmitModel` and `submit_media_request`.
- Existing route ordering around the moved endpoint is preserved.
- Verification passes:
  - `uv run python -m compileall` for changed Python files.
  - An import/route compatibility check through `uv run python -c ...` with UTF-8 output on Windows if needed.
  - Focused media request router boundary tests.
  - Full `uv run pytest tests/ -v`.
