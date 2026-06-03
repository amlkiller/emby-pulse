# Refactor notification user bot binding cache service

## Goal

Split user bot binding/cache helper responsibilities out of `app/domains/notifications/user_bot_service.py` into a focused notification domain service while preserving existing behavior and compatibility functions.

## Requirements

* Move the helper implementations for user binding lookup/update, channel binding lookup/update, blacklist lookup/write, bot-user tracking, and Emby account existence cache into `app/domains/notifications/user_bot_binding_service.py`.
* Keep legacy functions in `user_bot_service.py` (`_get_binding`, `_bind_user`, `_unbind_user`, `_is_blacklisted`, etc.) as compatibility wrappers.
* Preserve existing cache keys, TTL semantics, thread locking behavior, DAO side effects, media API status-code behavior, network-error fallback, and logging behavior.
* Preserve monkeypatch-friendly module-level globals in `user_bot_service.py` where existing tests/callers patch `user_bot_service.user_bot_dao`, `media_api`, `time`, or caches.
* Add focused tests that prove the compatibility wrappers delegate through the new service while still observing monkeypatches to legacy `user_bot_service.*` globals.

## Acceptance Criteria

* [ ] `user_bot_service.py` no longer owns the binding/cache helper implementation bodies.
* [ ] New `user_bot_binding_service.py` owns the implementation and exposes provider configuration.
* [ ] Legacy `user_bot_service._*` helper functions still exist and preserve behavior.
* [ ] Focused tests cover cache hit/miss, bind/unbind cache mutation, channel binding composition, blacklist cache behavior, bot-user tracking fallbacks, and Emby account network fallback.
* [ ] Full test suite passes.
* [ ] Code/test changes are committed separately from Trellis archive and journal bookkeeping.

## Definition of Done

* Compile changed Python files with `uv run python -m compileall`.
* Run focused notification/user-bot tests.
* Run `uv run pytest tests/ -v`.
* Run `git diff --check`.
* Commit the code/test slice.
* Archive the Trellis task and record the session journal.

## Technical Approach

Use the same compatibility-preserving provider pattern established in prior domain splits. The new service should default to current DAO/media/logger/time/lock/cache globals, while `user_bot_service.py` configures providers with lambdas that resolve legacy globals at call time.

## Out of Scope

* Changing Telegram command handling.
* Changing polling or scheduler lifecycle.
* Refactoring registration quota logic, point games, media requests, or command dispatch.
* Changing DAO SQL or database schema.

## Technical Notes

* Architecture audit target: `docs/架构审计.md` P2 item 5, domain files still too large and mixed-responsibility.
* Applicable specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/backend/error-handling.md`, `.trellis/spec/guides/code-reuse-thinking-guide.md`.
