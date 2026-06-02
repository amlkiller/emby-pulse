# Playback Public Service Facade for Keep Alive

## Goal

Reduce plugin-to-domain-internal coupling from the architecture audit by moving the keep-alive plugin off the private `app.domains.playback.stats_queries` module and onto a narrow playback public facade.

## Requirements

* Add `app/domains/playback/public_service.py` as the public cross-domain boundary for playback query behavior needed by external callers.
* Preserve current keep-alive behavior and return shapes by delegating `get_user_play_summary(...)` directly to the existing playback query implementation.
* Update `app/plugins/keep_alive/plugin.py` to use the playback public facade instead of importing `app.domains.playback.stats_queries`.
* Add focused tests proving the facade delegates correctly and the keep-alive plugin no longer imports private playback query modules.

## Acceptance Criteria

* [ ] `keep_alive` calls `playback.public_service.get_user_play_summary(...)`.
* [ ] `app/domains/playback/public_service.py` delegates to `stats_queries.get_user_play_summary(...)`.
* [ ] Focused facade/boundary tests pass.
* [ ] Changed Python files compile through `uv run --with-requirements requirements.txt`.
* [ ] Full pytest suite passes.

## Definition of Done

* Behavior remains compatible with existing keep-alive checks.
* No new private playback query imports are introduced in plugins.
* Work is committed as one coherent refactor commit, then the Trellis task is archived and journaled.

## Technical Approach

Create a thin playback public service module that imports `stats_queries` within the playback domain and exposes the single query needed by keep-alive. Replace the plugin import with `from app.domains.playback import public_service as playback_service`, then call `playback_service.get_user_play_summary(...)`.

## Out of Scope

* Refactoring playback stats internals.
* Moving playback schema/query logic.
* Changing keep-alive scheduling, thresholds, notifications, or API responses.
* Broad plugin admin-auth import cleanup.

## Technical Notes

* Audit source: `docs/架构审计.md` P2 item 6 recommends public service/facade boundaries for cross-domain and plugin calls.
* Existing facade pattern examples: `notifications.public_service`, `users.public_service`, `media_requests.public_service`, `reports.public_service`, `system.public_service`.
* Current private import site: `app/plugins/keep_alive/plugin.py` imports `app.domains.playback.stats_queries.get_user_play_summary`.
