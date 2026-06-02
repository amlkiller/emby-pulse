# Refactor Media Request Community Cache

## Context

`docs/架构审计.md` lists `app/domains/media_requests/router.py` as a large mixed-responsibility domain file. The router currently owns HTTP endpoints, cache state, cache refresh orchestration, external calls, and bootstrap service hooks.

## Goal

Extract the user community cache responsibility from `media_requests/router.py` into a domain-local service module while preserving all existing route behavior and compatibility imports.

## Scope

- Move community cache state, cache helpers, background refresh implementation, and refresh-loop lifecycle into a named media request service module.
- Keep `router.py` compatibility exports for existing tests, bootstrap imports, system diagnostics, and route handlers.
- Preserve route URLs, response shapes, cache TTL values, refresh timings, logging behavior, and service lifecycle behavior.
- Do not change media request database schema, notification behavior, or request/feedback workflows.

## Acceptance Criteria

- `media_requests/router.py` is smaller and delegates community cache behavior to a domain-local service module.
- Existing callers through `media_requests.router` still work.
- Focused compile/import/lifecycle tests pass.
- Full `uv run pytest tests/ -v` passes.
- Changes are committed and the Trellis task is archived/recorded.
