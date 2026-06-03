# Refactor notification user bot registration quota service

## Goal

Split registration quota, user-count cache, batch-used persistence, and batch flush loop helpers out of `app/domains/notifications/user_bot_service.py` into a focused notification domain service while preserving existing behavior and compatibility globals.

## Requirements

* Move helper implementations for batch-used loading/flushing, batch flush thread lifecycle, cached Emby user counts, quota slot reserve/release, and batch-used incrementing into `app/domains/notifications/user_bot_registration_quota_service.py`.
* Keep legacy functions in `user_bot_service.py` (`_reserve_quota_slot`, `_release_quota_slot`, `_inc_batch_used`, `_start_batch_flush_thread`, etc.) as compatibility wrappers.
* Preserve existing module-level state objects in `user_bot_service.py` so tests and callers that patch/reset `_quota_lock`, `_batch_used_mem`, `_batch_flush_thread`, `_user_count_cache`, `media_api`, or settings functions still work.
* Preserve concurrency behavior, notification side effects, auto-close behavior, logger behavior, and lifecycle stop hook semantics.
* Add focused tests proving compatibility wrappers observe legacy monkeypatches and still update old state globals.

## Acceptance Criteria

* [ ] `user_bot_service.py` no longer owns implementation bodies for registration quota helpers.
* [ ] New `user_bot_registration_quota_service.py` owns the implementation and exposes provider configuration.
* [ ] Existing concurrency and lifecycle tests still pass.
* [ ] New boundary tests cover load/flush, cached user count behavior, reserve/release, batch increment, and flush thread lifecycle via old `user_bot_service.*` globals.
* [ ] Full test suite passes.
* [ ] Code/test changes are committed separately from Trellis archive and journal bookkeeping.

## Definition of Done

* Compile changed Python files with `uv run python -m compileall`.
* Run focused registration quota, concurrency, and lifecycle tests.
* Run `uv run pytest tests/ -v`.
* Run `git diff --check`.
* Commit the code/test slice.
* Archive the Trellis task and record the session journal.

## Technical Approach

Use the provider compatibility pattern from recent domain splits. The new service should default to local state but be configured by `user_bot_service.py` with lambdas and setter callbacks that operate on the old module globals at request time.

## Out of Scope

* Rewriting `_do_register` or invitation-code registration.
* Changing quota policy, thresholds, close-notification text, or media user filtering.
* Changing Telegram polling, command dispatch, or worker lifecycle outside batch flush helpers.
* Changing config reader/writer contracts.

## Technical Notes

* Architecture audit target: `docs/架构审计.md` P2 item 5, domain files still too large and mixed-responsibility.
* Existing regression coverage: `tests/test_reg_concurrency.py` and `tests/test_bootstrap_stop_hooks.py::test_user_bot_worker_threads_stop_and_restart`.
* Applicable specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/guides/code-reuse-thinking-guide.md`.
