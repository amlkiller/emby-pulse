# Refactor Notification User Bot Polling

## Goal

Split the `UserBot` Telegram long-polling responsibility out of `app/domains/notifications/user_bot_service.py` into a domain-local named service module, reducing mixed responsibilities in the large notification user bot file while preserving existing runtime behavior.

## Requirements

* Extract the polling loop that calls Telegram `getUpdates`, advances the update offset, and submits message/callback handlers to the existing queue into a new `app/domains/notifications/*_service.py` module.
* Keep `UserBot.start()` / `UserBot.stop()` behavior stable, including thread ownership, offset storage, queue-full user feedback, and stop-event waits.
* Preserve existing calls to `telegram_client`, `get_safe_proxies()`, `_submit_task()`, `_send()`, and `logger` through provider injection or equivalent lazy lookup so legacy globals remain monkeypatchable.
* Do not change message handling, callback handling, command routing, Telegram request payloads, or public function signatures.

## Acceptance Criteria

* [ ] `user_bot_service.py` delegates polling loop execution to the extracted notification polling service.
* [ ] Existing lifecycle stop-event checks remain covered.
* [ ] New boundary coverage verifies polling still submits messages/callbacks and reports queue-full message back to the chat.
* [ ] Changed modules compile and import through `uv run`.
* [ ] Full `uv run pytest tests/ -v` passes before the work commit.

## Definition of Done

* Run focused compile/import checks for changed files.
* Run focused polling/lifecycle tests.
* Run the full test suite.
* Commit code/test changes separately from Trellis archive and journal bookkeeping.
* Archive the Trellis task and record a session journal entry referencing the work commit.

## Technical Approach

Create a small polling service with `run_polling_loop(offset_provider, offset_setter, message_handler_provider, callback_handler_provider, running_provider, stop_event)`. Configure dependencies from `user_bot_service.py` with lambdas so monkeypatches of legacy globals are honored at call time. Keep `UserBot` as the owner of thread handles and `offset`.

## Decision (ADR-lite)

Context: `UserBot` still owns lifecycle, Telegram polling, message dispatch, callback dispatch, group welcome handling, and lottery draw behavior.

Decision: Extract only Telegram update polling in this slice. Keep handler methods on `UserBot` and pass them into the polling service as callables.

Consequences: This reduces one runtime responsibility without changing command behavior. Future slices can split private/group message dispatch or callback dispatch independently.

## Out of Scope

* Moving `UserBot` class out of `user_bot_service.py`.
* Refactoring `_on_message()` or `_on_callback()`.
* Changing Telegram timeout, proxy, queue, or error handling semantics.
* Changing lottery draw or scheduler behavior.

## Technical Notes

* Architecture audit target: `docs/架构审计.md` P2 item 5, large mixed-responsibility domain files.
* Applicable specs: `.trellis/spec/backend/index.md`, `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/backend/logging-guidelines.md`, `.trellis/spec/guides/index.md`.
* Primary file inspected: `app/domains/notifications/user_bot_service.py`.
