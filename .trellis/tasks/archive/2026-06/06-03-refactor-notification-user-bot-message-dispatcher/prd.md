# Refactor Notification User Bot Message Dispatcher

## Goal

Split the `UserBot` Telegram message dispatcher out of `app/domains/notifications/user_bot_service.py` into a domain-local named service module, reducing mixed responsibilities in the large notification user bot file while preserving existing message behavior.

## Requirements

* Extract the body of `UserBot._on_message()` into a new `app/domains/notifications/*_service.py` module.
* Keep `UserBot._on_message(msg)` as a compatibility wrapper that delegates to the new service.
* Preserve channel-identity handling, group command filtering, private command routing, restriction checks, binding checks, user state transitions, and existing command wrapper calls.
* Configure dependencies from `user_bot_service.py` through lazy providers so legacy globals and wrapper functions remain monkeypatchable.
* Keep `UserBot._on_new_chat_members()` on the class for this slice; call it through a provider from the message dispatcher.
* Do not change polling, callback dispatch, scheduler, lottery draw, or command implementation behavior.

## Acceptance Criteria

* [ ] `user_bot_service.py` delegates message handling to the extracted message dispatcher service.
* [ ] New boundary coverage verifies representative group, private unbound state, and bound command branches through legacy monkeypatches.
* [ ] Changed modules compile and import through `uv run`.
* [ ] Full `uv run pytest tests/ -v` passes before the work commit.

## Definition of Done

* Run focused compile/import checks for changed files.
* Run focused message dispatcher tests.
* Run the full test suite.
* Commit code/test changes separately from Trellis archive and journal bookkeeping.
* Archive the Trellis task and record a session journal entry referencing the work commit.

## Technical Approach

Create `user_bot_message_dispatcher_service.py` with `handle_message(msg, new_chat_members_handler=None)`. The module will use `set_dependency_providers(...)` matching existing notification user bot extraction patterns, with providers for logger, rate checks, group settings, binding/account helpers, user state, command wrappers, and message cleanup.

## Decision (ADR-lite)

Context: `UserBot` still owns lifecycle, message dispatch, group welcome handling, and lottery draw behavior.

Decision: Extract only Telegram message dispatch in this slice. Keep group welcome handling as a method on `UserBot` and invoke it via provider/wrapper.

Consequences: This removes the largest remaining dispatcher from `user_bot_service.py` while keeping command behavior and class compatibility stable. New chat member handling and lottery draw can be split later.

## Out of Scope

* Moving `UserBot` class out of `user_bot_service.py`.
* Moving `_on_new_chat_members()`.
* Refactoring command implementations or command wrapper functions.
* Changing group whitelist, command alias, binding, or restriction behavior.

## Technical Notes

* Architecture audit target: `docs/架构审计.md` P2 item 5, large mixed-responsibility domain files.
* Applicable specs: `.trellis/spec/backend/index.md`, `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/backend/logging-guidelines.md`, `.trellis/spec/guides/index.md`.
* Primary file inspected: `app/domains/notifications/user_bot_service.py`.
