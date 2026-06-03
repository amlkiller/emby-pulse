# Refactor notification user bot concurrency helpers

## Goal

Split user bot rate-limit and username-lock helpers out of `app/domains/notifications/user_bot_service.py` into a focused notification domain service while preserving existing behavior and compatibility globals.

## Requirements

* Move implementation for `_rate_check` and `_get_username_lock` into `app/domains/notifications/user_bot_concurrency_service.py`.
* Keep legacy functions and module-level state in `user_bot_service.py` so existing callers and tests can continue to patch `_rate_limit`, `_username_locks`, `_username_locks_lock`, `_USERNAME_LOCK_MAX_SIZE`, `threading`, `time`, and `logger`.
* Preserve rate-limit timestamp behavior, cooldown comparison, username lock reuse, max-size cleanup behavior, logger message, and lock factory behavior.
* Configure the new service through provider callbacks that read `user_bot_service.py` globals at call time.
* Add focused boundary tests proving old wrappers observe legacy monkeypatches and update legacy state.

## Acceptance Criteria

* [ ] `user_bot_service.py` no longer owns implementation bodies for rate-limit and username-lock helpers.
* [ ] New `user_bot_concurrency_service.py` owns implementation and exposes provider configuration.
* [ ] New boundary tests cover rate pass/fail timestamp behavior, lock reuse, lock creation through patched threading, and max-size cleanup/logging through old `user_bot_service.*` globals.
* [ ] Full test suite passes.
* [ ] Code/test changes are committed separately from Trellis archive and journal bookkeeping.

## Definition of Done

* Compile changed Python files with `uv run python -m compileall`.
* Run focused concurrency helper boundary tests.
* Run `uv run pytest tests/ -v`.
* Run `git diff --check`.
* Commit the code/test slice.
* Archive the Trellis task and record the session journal.

## Technical Approach

Use the provider compatibility pattern from recent notification user bot splits. The new service should default to local state but be configured by `user_bot_service.py` with lambdas and setter callbacks that operate on old module globals at request time.

## Out of Scope

* Rewriting registration, queueing, quota, Telegram, restriction, binding, or command handling.
* Changing cooldown values, username normalization, username validation, or registration flow.
* Changing thread pool or registration semaphore behavior.

## Technical Notes

* Architecture audit target: `docs/架构审计.md` P2 item 5, domain files still too large and mixed-responsibility.
* Applicable specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/guides/code-reuse-thinking-guide.md`.
