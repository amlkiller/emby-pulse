# Refactor Notification User Bot Callback Dispatcher

## Goal

Split the `UserBot` Telegram inline callback dispatcher out of `app/domains/notifications/user_bot_service.py` into a domain-local named service module, reducing mixed responsibilities in the large notification user bot file while preserving existing button behavior.

## Requirements

* Extract the body of `UserBot._on_callback()` into a new `app/domains/notifications/*_service.py` module.
* Keep `UserBot._on_callback(cq)` as a compatibility wrapper that delegates to the new service.
* Preserve all existing callback data branches, messages, reply markup, rate checks, restriction checks, binding checks, and command callback calls.
* Configure dependencies from `user_bot_service.py` through lazy providers so legacy globals and wrapper functions remain monkeypatchable.
* Do not change message dispatch, polling, scheduler, or command implementation behavior.

## Acceptance Criteria

* [ ] `user_bot_service.py` delegates callback query handling to the extracted callback dispatcher service.
* [ ] New boundary coverage verifies representative unbound, bound, and pattern-based callback branches through legacy monkeypatches.
* [ ] Changed modules compile and import through `uv run`.
* [ ] Full `uv run pytest tests/ -v` passes before the work commit.

## Definition of Done

* Run focused compile/import checks for changed files.
* Run focused callback dispatcher tests.
* Run the full test suite.
* Commit code/test changes separately from Trellis archive and journal bookkeeping.
* Archive the Trellis task and record a session journal entry referencing the work commit.

## Technical Approach

Create `user_bot_callback_dispatcher_service.py` with `handle_callback(cq)`. The module will use `set_dependency_providers(...)` matching existing notification user bot service extraction patterns, with providers for `_tg_api`, `_send`, `_edit`, `_rate_check`, `_check_user_restrictions`, `_get_binding`, command callbacks, `_user_state`, and `_main_menu_keyboard`.

## Decision (ADR-lite)

Context: `UserBot` still owns lifecycle, message dispatch, callback dispatch, group welcome handling, and lottery draw behavior.

Decision: Extract only inline callback dispatch in this slice. Keep the wrapper method and all legacy helper names in `user_bot_service.py`.

Consequences: This reduces one major dispatcher responsibility while keeping external tests/callers compatible. Private/group message dispatch and lottery draw can be split in later slices.

## Out of Scope

* Moving `UserBot` class out of `user_bot_service.py`.
* Refactoring `_on_message()`.
* Renaming callback data values or changing Telegram button messages.
* Changing command implementations invoked by callbacks.

## Technical Notes

* Architecture audit target: `docs/架构审计.md` P2 item 5, large mixed-responsibility domain files.
* Applicable specs: `.trellis/spec/backend/index.md`, `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/backend/logging-guidelines.md`, `.trellis/spec/guides/index.md`.
* Primary file inspected: `app/domains/notifications/user_bot_service.py`.
