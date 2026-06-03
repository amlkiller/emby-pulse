# Refactor notification user bot code registration handler

## Goal

Reduce `app/domains/notifications/user_bot_service.py` mixed responsibilities by moving the invitation-code account creation handler into the existing focused user bot code command service while preserving the legacy helper name and dispatcher behavior.

## Requirements

* Extract `_do_code_register` from `user_bot_service.py` into `app/domains/notifications/user_bot_code_commands_service.py`.
* Keep a legacy `_do_code_register(chat_id, tg_user_id, custom_name, code, days, tpl_id, routes=None, route_mode=None, tg_username="", tg_display_name="")` wrapper in `user_bot_service.py`.
* Wire dependency providers from `user_bot_service.py` using lambdas that read legacy globals at call time.
* Preserve registration queue entry/leave behavior, username validation, user-state rollback prompts, password generation, username lock use, Emby create/password/policy calls, invitation claim/rollback/finalization, cache invalidation, bot binding, success message, admin/system notifications, logger messages, safe-error handling, and existing swallowed optional failures.
* Add boundary tests that call through `user_bot_service._do_code_register` and monkeypatch legacy globals.

## Acceptance Criteria

* [ ] `_do_code_register` delegates to the code command service and preserves queue rejection, validation, duplicate username, claim failure, Emby create failure rollback, success, and exception behavior where covered by focused tests.
* [ ] Existing `cmd_code`, `_restore_invitation_code`, and `/code` dispatcher behavior remains unchanged.
* [ ] Focused tests pass with `uv run pytest`.
* [ ] Changed Python files compile with `uv run python -m compileall`.
* [ ] Full test suite passes before commit.

## Definition of Done

* Code and tests are committed in one work commit.
* Trellis task is archived after the work commit.
* Session journal records the work commit hash.

## Technical Approach

Follow the established user bot service extraction pattern:

* Extend `user_bot_code_commands_service.py` with `do_code_register`.
* Add dependency providers for queue callbacks, username lock lookup, Emby media API, bind callback, password/date helpers, and existing DAO/state/send/logger dependencies.
* Update `user_bot_service.py` provider wiring.
* Replace the legacy `_do_code_register` body with a thin wrapper.
* Keep command dispatch and user state action names unchanged.

## Decision (ADR-lite)

Context: `cmd_code` and `restore_invitation_code` are already in `user_bot_code_commands_service.py`, but the actual code-registration account creation workflow still lives in the large compatibility module.

Decision: Move only `_do_code_register` into the existing code command service and keep the old helper as a compatibility wrapper.

Consequences: The large user bot service shrinks further without changing the user-state dispatcher or public helper names. Open-registration `_do_register` remains a separate follow-up slice.

## Out of Scope

* Open-registration `_do_register` extraction.
* `/code` command parsing changes.
* Invitation DAO/schema changes.
* Emby policy or notification behavior changes.
* Fixing pre-existing optional-notification swallowing behavior.

## Technical Notes

* Audit source: `docs/架构审计.md` P2 item 5.
* Existing extraction patterns: `user_bot_code_commands_service.py`, `user_bot_basic_commands_service.py`, `user_bot_registration_queue_service.py`.
* Relevant specs: `.trellis/spec/backend/index.md`, `directory-structure.md`, `quality-guidelines.md`, `error-handling.md`, `logging-guidelines.md`, `.trellis/spec/guides/index.md`.
