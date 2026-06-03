# Refactor notification user bot registration queue service

## Goal

Split the user bot registration FIFO queue and task queue counters from `app/domains/notifications/user_bot_service.py` into a focused notification domain service while preserving existing behavior and compatibility globals.

## Requirements

* Move implementation for `_submit_task`, `_get_queue_status`, `_enter_reg_queue`, and `_leave_reg_queue` into `app/domains/notifications/user_bot_registration_queue_service.py`.
* Keep legacy functions and module-level state in `user_bot_service.py` so existing callers and tests can continue to reset or monkeypatch `_active_tasks`, `_waiting_count`, `_reg_waiters`, `_reg_active`, `_reg_sema`, and lock objects.
* Preserve FIFO registration queue behavior, waiting-position messages, timeout behavior, BoundedSemaphore release handling, logger behavior, and executor submission behavior.
* Configure the new service through provider callbacks that read `user_bot_service.py` globals at call time.
* Add focused boundary tests proving old wrappers observe legacy monkeypatches and update legacy state.

## Acceptance Criteria

* [ ] `user_bot_service.py` no longer owns implementation bodies for task queue and registration queue helpers.
* [ ] New `user_bot_registration_queue_service.py` owns implementation and exposes provider configuration.
* [ ] `tests/test_reg_concurrency.py` continues to pass.
* [ ] New boundary tests cover queue status, task submission counter transitions, registration queue enter/leave, timeout messaging, and semaphore release error logging through old `user_bot_service.*` globals.
* [ ] Full test suite passes.
* [ ] Code/test changes are committed separately from Trellis archive and journal bookkeeping.

## Definition of Done

* Compile changed Python files with `uv run python -m compileall`.
* Run focused registration queue/concurrency tests.
* Run `uv run pytest tests/ -v`.
* Run `git diff --check`.
* Commit the code/test slice.
* Archive the Trellis task and record the session journal.

## Technical Approach

Use the provider compatibility pattern from recent notification user bot splits. The new service should default to local state but be configured by `user_bot_service.py` with lambdas and setter callbacks that operate on old module globals at request time.

## Out of Scope

* Rewriting `_do_register`, registration quota policy, or invitation-code registration.
* Changing Telegram messages, queue limits, semaphore sizes, or timeout values.
* Changing `ThreadPoolExecutor` construction or user bot worker lifecycle outside the queue helper functions.

## Technical Notes

* Architecture audit target: `docs/架构审计.md` P2 item 5, domain files still too large and mixed-responsibility.
* Existing regression coverage: `tests/test_reg_concurrency.py`.
* Applicable specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/guides/code-reuse-thinking-guide.md`.
