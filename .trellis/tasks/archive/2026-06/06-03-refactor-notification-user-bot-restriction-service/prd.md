# Refactor notification user bot restriction service

## Goal

Split user bot registration restriction checks and restriction-cache helpers out of `app/domains/notifications/user_bot_service.py` into a focused notification domain service while preserving existing behavior and compatibility globals.

## Requirements

* Move implementation for `_check_user_in_chat`, `_check_user_restrictions`, `_clear_restriction_cache`, and `_format_restriction_message` into `app/domains/notifications/user_bot_restriction_service.py`.
* Keep legacy functions and module-level state in `user_bot_service.py` so existing callers and tests can continue to patch `_restriction_cache`, `_restriction_cache_lock`, `telegram_client`, settings readers, logger, and time.
* Preserve required channel/group checking, cache TTL behavior, failed-check message shape, missing item labels, Telegram API calls, exception handling, and cache invalidation behavior.
* Configure the new service through provider callbacks that read `user_bot_service.py` globals at call time.
* Add focused boundary tests proving old wrappers observe legacy monkeypatches and update legacy state.

## Acceptance Criteria

* [ ] `user_bot_service.py` no longer owns implementation bodies for restriction-check helpers.
* [ ] New `user_bot_restriction_service.py` owns implementation and exposes provider configuration.
* [ ] New boundary tests cover channel/group checks, cache hit behavior, cache clear behavior, disabled restrictions behavior, and formatted restriction messages through old `user_bot_service.*` globals.
* [ ] Full test suite passes.
* [ ] Code/test changes are committed separately from Trellis archive and journal bookkeeping.

## Definition of Done

* Compile changed Python files with `uv run python -m compileall`.
* Run focused restriction service boundary tests.
* Run `uv run pytest tests/ -v`.
* Run `git diff --check`.
* Commit the code/test slice.
* Archive the Trellis task and record the session journal.

## Technical Approach

Use the provider compatibility pattern from recent notification user bot splits. The new service should default to local state but be configured by `user_bot_service.py` with lambdas and setter callbacks that operate on old module globals at request time.

## Out of Scope

* Rewriting registration command flow or `_do_register`.
* Changing Telegram restriction API contracts, message text, cache TTL settings, or group/channel settings readers.
* Changing bot polling, task queues, quota policy, or binding/cache helpers.

## Technical Notes

* Architecture audit target: `docs/架构审计.md` P2 item 5, domain files still too large and mixed-responsibility.
* Applicable specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/guides/code-reuse-thinking-guide.md`.
