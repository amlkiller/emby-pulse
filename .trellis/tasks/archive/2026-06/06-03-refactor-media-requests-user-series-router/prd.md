# Refactor Media Requests User Series Router

## Goal

Continue the P2 architecture audit work by splitting one more responsibility out of `app/domains/media_requests/router.py` without changing runtime behavior.

## Scope

- Extract the user series endpoints from `app/domains/media_requests/router.py` into a domain-local child router module.
- Target endpoints:
  - `GET /api/user/my_series`
  - `POST /api/user/my_series/refresh`
- Move only the helper/model code required by those endpoints when it is not shared by other remaining routes.
- Include the new child router from `media_requests/router.py` at the same relative route position.
- Preserve old-module compatibility exports for moved functions/helpers that tests or external callers may still import or monkeypatch.
- Preserve dependency monkeypatch behavior by resolving old `media_requests.router` globals through provider callables at request time.

## Non-Goals

- Do not change request/response payloads, auth behavior, cache behavior, route paths, or route methods.
- Do not refactor update request submission, registration, discovery, management, gaps, DAO, or notification behavior in this slice.
- Do not introduce new cross-domain imports beyond dependencies already used by `media_requests/router.py`.
- Do not change database schema or external API transport behavior.

## Acceptance Criteria

- `app/domains/media_requests/router.py` is smaller and delegates user series endpoints to a new child router module.
- The two user series routes remain present under the main `media_requests.router.router`.
- Compatibility imports from `app.domains.media_requests.router` continue to expose moved route/helper functions needed by existing tests.
- Existing route ordering around the moved endpoints is preserved.
- Verification passes:
  - `uv run python -m compileall` for changed Python files.
  - An import/route compatibility check through `uv run python -c ...` with UTF-8 output on Windows if needed.
  - Focused media request router boundary tests.
  - Full `uv run pytest tests/ -v`.
