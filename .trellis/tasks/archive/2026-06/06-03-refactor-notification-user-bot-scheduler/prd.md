# Refactor Notification User Bot Scheduler

## Goal

Split the `UserBot` background scheduler responsibility out of `app/domains/notifications/user_bot_service.py` into a domain-local named service module, reducing mixed responsibilities in the large notification user bot file while preserving existing runtime behavior.

## Requirements

* Extract the scheduler loop that handles lottery auto-draw timing and expired PK invitation cleanup into a new `app/domains/notifications/*_service.py` module.
* Keep `UserBot.start()` / `UserBot.stop()` behavior stable, including one scheduler thread, the existing stop event semantics, and the 30-second initial wait / 60-second loop waits.
* Preserve existing calls to `do_lottery_draw()`, `point_dao`, `_tg_api()`, and logging behavior through provider injection or equivalent lazy lookup so compatibility globals remain monkeypatchable.
* Do not change Telegram command handling, callback handling, lottery draw business logic, or public function signatures.

## Acceptance Criteria

* [ ] `user_bot_service.py` delegates scheduler loop execution to the extracted notification scheduler service.
* [ ] Existing tests pass without behavior changes.
* [ ] Changed modules compile and import through `uv run`.
* [ ] Full `uv run pytest tests/ -v` passes before the work commit.

## Definition of Done

* Run focused compile/import checks for changed files.
* Run the full test suite.
* Commit code/test changes separately from Trellis archive and journal bookkeeping.
* Archive the Trellis task and record a session journal entry referencing the work commit.

## Technical Approach

Create a small service module that exposes a `run_scheduler_loop(running_provider, stop_event)` function. Configure dependencies from `user_bot_service.py` with lambdas so monkeypatches of legacy globals such as `point_dao`, `_tg_api`, and `do_lottery_draw` are honored at call time.

## Decision (ADR-lite)

Context: `UserBot` currently owns lifecycle, Telegram polling, message dispatch, callback dispatch, group welcome handling, and scheduled background jobs.

Decision: Extract only the scheduled background job loop in this slice. Keep thread ownership in `UserBot` so start/stop lifecycle remains unchanged.

Consequences: This reduces one responsibility without changing public behavior. Further slices can split polling, private/group message dispatch, or callback dispatch separately.

## Out of Scope

* Moving `UserBot` class out of `user_bot_service.py`.
* Refactoring message or callback command dispatch.
* Changing lottery draw logic or PK invitation persistence behavior.
* Adding new domain facades.

## Technical Notes

* Architecture audit target: `docs/架构审计.md` P2 item 5, large mixed-responsibility domain files.
* Applicable specs: `.trellis/spec/backend/index.md`, `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/backend/error-handling.md`, `.trellis/spec/backend/logging-guidelines.md`, `.trellis/spec/guides/index.md`.
* Primary file inspected: `app/domains/notifications/user_bot_service.py`.
