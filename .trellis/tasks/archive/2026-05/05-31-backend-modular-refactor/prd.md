# Backend modular refactor plan

## Goal

Restructure the backend into clearer modules to reduce duplication, improve maintainability, and make future changes safer without losing current behavior.

## What I already know

* The backend lives under `app/` and is currently organized into `core/`, `routers/`, `services/`, `plugins/`, `schemas/`, and `utils/`.
* `app/main.py` is a very large application entrypoint that wires startup behavior, database setup, middleware, route registration, and a separate user-portal ASGI wrapper.
* Several routers and services are very large, especially `app/routers/users.py`, `app/routers/points.py`, `app/routers/media_request.py`, `app/routers/stats.py`, `app/services/bot_service.py`, and `app/services/user_bot_service.py`.
* There is an existing backend spec scaffold in `.trellis/spec/backend/index.md`, but the detailed guideline files are still empty.
* The repository already contains security and refactor-related notes in `docs/`, including `docs/SECURITY_AUDIT_2026-05-17.md` and `fixplan.md`.
* The project currently exposes an admin portal and a separate user portal on different ports.

## Assumptions (temporary)

* The main value is module boundaries and shared abstractions, not a complete rewrite.
* The work should target the backend only.

## Open Questions

* Which backend area is the highest priority: routers, services, shared infrastructure, or startup/bootstrap?
* Do we want a phased extraction plan or one larger structural change?
* Which `app/main.py` responsibilities should be extracted in the first implementation slice?

## Requirements (evolving)

* Preserve existing external behavior in the first refactor pass:
  * Keep current routes and response formats.
  * Keep admin/user portal behavior and port isolation semantics.
  * Avoid business-rule changes unless needed to preserve behavior during extraction.
* Start with startup/bootstrap and core shared infrastructure only.
* Use `app/bootstrap` for application wiring and startup orchestration.
* Keep `app/core` for reusable cross-cutting runtime helpers.
* Reduce repeated code in large routers/services.
* Separate concerns so startup, security, persistence, and feature logic are easier to reason about.
* Keep module responsibilities explicit and stable.

## Acceptance Criteria (evolving)

* [ ] Backend modules have clearer boundaries and less duplicated logic.
* [ ] Existing behavior stays stable; breaking changes are out of scope for the first pass.
* [ ] Refactor decisions are documented clearly enough for future work.

## Definition of Done (team quality bar)

* Tests added or updated where behavior changes.
* Lint / typecheck / CI green.
* Docs updated if conventions or boundaries change.

## Out of Scope (explicit)

* Frontend changes.
* Feature expansion unrelated to backend structure.
* A full rewrite of the application.

## Technical Notes

* `app/main.py` currently combines app bootstrap, middleware, database init, security checks, and dual-portal setup.
* `app/main.py` also owns global exception handling, CORS parsing, no-cache middleware, static/public mounts, route registration, plugin route registration, calendar notification service init, and the user-portal ASGI wrapper.
* Large backend files suggest repeated patterns that likely need shared helpers or module extraction.
* Admin checks are repeated across many routers via `is_admin_user(request)` and ad hoc session checks; `app/core/security.py` already contains some dependency-style helpers.
* Routers frequently import `app.core.database`, `app.core.media_adapter`, `app.services.bot_service`, and `app.services.user_bot_service` directly, indicating tight coupling between HTTP handlers, persistence, media API access, and bot side effects.
* First implementation priority: extract `app/main.py` wiring into `app/bootstrap` while keeping existing behavior unchanged.
* Relevant docs: `README.md`, `fixplan.md`, `docs/SECURITY_AUDIT_2026-05-17.md`.
