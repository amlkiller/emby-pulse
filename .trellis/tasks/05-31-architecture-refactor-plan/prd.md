# Architecture Refactor Plan

## Goal

Define the architecture refactor target for EmbyPulse-Pro and implement the first database-boundary sample migration. The implementation focus is limited to `app/infra/db`, `app/queries`, `app/dao`, `app/routers/history.py`, and `app/routers/api_tokens.py`.

## What I Already Know

- The project is a FastAPI + SQLite application for Emby/Jellyfin management and monitoring.
- `app/main.py` has already been split into a thin entrypoint plus `app/bootstrap/`.
- The largest current coupling point is database access: `app/core/database.py` combines connection management, dual database routing, API passthrough, migrations, schema creation, query stats, and system notification writes.
- `app/core/database.py` and `app/core/db_schemas.py` both define database schema knowledge, creating duplicate sources of truth.
- Heavy route/service modules include `points.py`, `media_request.py`, `users.py`, `stats.py`, `messages.py`, `bot_service.py`, and `user_bot_service.py`.
- The user confirmed the refactor should prioritize infrastructure boundaries before business-domain modularization.
- The user confirmed `query_db()` should not be retained as a compatibility facade; the final target is complete removal.
- The user confirmed migration should be phased through representative modules first, then expanded in batches.
- The user confirmed Query Service / DAO style over a full Repository abstraction.
- The user confirmed new database infrastructure should live under `app/infra/db/`.
- The user confirmed `app/queries/` and `app/dao/` are acceptable transition directories before full business-domain modularization.
- The user confirmed external client adapters should move under `app/infra/clients/`, but as a second-stage goal after the database refactor.
- The user confirmed `cfg.get()` / `cfg.set()` cleanup should be a third-stage goal, not part of the first database refactor stage.
- The user confirmed plugins are not in first-stage migration scope, but plugin compatibility must constrain the new database API design.
- The user confirmed complete `query_db()` removal is the final target, while first-stage completion can be representative-module validation.
- The user confirmed first-stage representative modules should be `app/routers/history.py` and `app/routers/api_tokens.py`.
- The user confirmed no formal ADR is needed at this stage.
- The user asked to proceed with the refactor after accepting the architecture plan.

## Requirements

- `架构.md` must describe the current architecture pressure points and the refactor target.
- The database refactor target must explicitly remove `query_db()` rather than preserve it as a long-term facade.
- The migration strategy must use representative modules first, then batch migration.
- The data access style must use Query Service / DAO patterns suited to SQL and statistics-heavy access.
- New database infrastructure should be planned under `app/infra/db/`, with scenario query/DAO modules outside `app/core/`.
- `app/queries/` and `app/dao/` should be treated as transition directories, not the final business-domain layout.
- External clients for Emby/Jellyfin, TMDB, Telegram, WeCom, and MoviePilot should be planned as second-stage infrastructure adapters under `app/infra/clients/`.
- Configuration access cleanup should be planned as a third-stage effort using scenario-specific settings boundaries.
- Plugins should not be migrated in the first stage, but the database API must provide a viable migration path for plugin state/config/log access.
- First-stage completion should require the new database boundary and representative migrated modules, not full-repo `query_db()` removal.
- First-stage representative migrations should target `history.py` for playback queries and `api_tokens.py` for system CRUD.
- No ADR should be created until implementation hardens the `app/infra/db` public API and the decision becomes harder to reverse.
- First-stage implementation should keep HTTP routes, response shapes, database data compatibility, and external behavior stable.
- The first-stage implementation should not migrate plugins, global config access, or external clients.

## Acceptance Criteria

- [x] `架构.md` captures all confirmed architecture decisions.
- [x] Open architecture questions are resolved one at a time with recommended answers.
- [x] The final plan distinguishes immediate refactor goals from later business-domain modularization.
- [x] The final plan identifies out-of-scope behavior changes.
- [x] The final plan separates first-stage completion criteria from the final removal target for `query_db()`.
- [x] `app/infra/db/` exists with initial database boundary modules.
- [x] `app/routers/history.py` no longer imports or calls `query_db()`.
- [x] `app/routers/api_tokens.py` no longer opens direct SQLite connections.
- [x] Existing tests or import checks pass.

## Out of Scope

- Changing API routes, response shapes, database schema, or runtime behavior.
- Creating full ADRs unless a decision becomes hard to reverse, surprising, and trade-off heavy enough to justify one.
- Migrating plugins.
- Cleaning all remaining `query_db()` usages across the full repository.
- Refactoring external clients or global `cfg` access.

## Technical Notes

- Source documents inspected: `CLAUDE.md`, `.trellis/spec/backend/directory-structure.md`, app file tree, bootstrap modules, database modules.
- Key current files: `app/core/database.py`, `app/core/db_schemas.py`, `app/core/db_manager.py`, `app/bootstrap/database.py`, `app/bootstrap/lifespan.py`, `app/bootstrap/routes.py`.
- Planning output: `架构.md`.
