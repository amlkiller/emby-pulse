# Refactor notification user bot open registration handler

## Goal

Reduce `app/domains/notifications/user_bot_service.py` mixed responsibilities by moving the open-registration account creation handler into a focused notification domain service while preserving the legacy helper name and dispatcher behavior.

## Requirements

* Extract `_do_register` from `user_bot_service.py` into a domain-local registration command/service module.
* Keep a legacy `_do_register(chat_id, tg_user_id, custom_name, tg_username="", tg_display_name="")` wrapper in `user_bot_service.py`.
* Wire dependency providers from `user_bot_service.py` using lambdas that read legacy globals at call time.
* Preserve registration queue entry/leave behavior, open-reg and quota checks, quota reservation/release semantics, username validation and state restore, password generation, username lock use, cached user lookup, duplicate confirmation refresh, Emby create/password/policy calls, expiry/routes persistence, binding, registration log best-effort behavior, success message, safe-error handling, and logger messages.
* Add boundary tests that call through `user_bot_service._do_register` and monkeypatch legacy globals.

## Acceptance Criteria

* [ ] `_do_register` delegates to the new service and preserves queue rejection, open-reg disabled, quota failures, validation, duplicate username, Emby create failure, success, registration-log failure, exception, and quota release behavior where covered by focused tests.
* [ ] Existing `cmd_register` and message-state dispatcher behavior remains unchanged.
* [ ] Focused tests pass with `uv run pytest`.
* [ ] Changed Python files compile with `uv run python -m compileall`.
* [ ] Full test suite passes before commit.

## Definition of Done

* Code and tests are committed in one work commit.
* Trellis task is archived after the work commit.
* Session journal records the work commit hash.

## Technical Approach

Follow the established user bot service extraction pattern:

* Create `app/domains/notifications/user_bot_open_registration_service.py`.
* Add dependency providers for queue callbacks, quota helpers/settings, username lock lookup, cached user callbacks, Emby media API, user DAO, user bot DAO, bind callback, menu callback, password/date helpers, and safe-error/logger dependencies.
* Update `user_bot_service.py` provider wiring.
* Replace the legacy `_do_register` body with a thin wrapper.
* Keep command dispatch and user state action names unchanged.

## Decision (ADR-lite)

Context: `cmd_register` is already in `user_bot_basic_commands_service.py`, but the actual open-registration account creation workflow still lives in the large compatibility module.

Decision: Move only `_do_register` into a focused open-registration service and keep the old helper as a compatibility wrapper.

Consequences: The large user bot service shrinks further while preserving the registration state machine. Broader registration/quota consolidation remains a follow-up slice.

## Out of Scope

* `/register` command prompt changes.
* Invitation-code registration changes.
* Registration quota algorithm changes.
* User DAO/schema changes.
* Fixing pre-existing best-effort logging/notification swallowing behavior.

## Technical Notes

* Audit source: `docs/架构审计.md` P2 item 5.
* Existing extraction patterns: `user_bot_code_commands_service.py`, `user_bot_registration_quota_service.py`, `user_bot_registration_queue_service.py`.
* Relevant specs: `.trellis/spec/backend/index.md`, `directory-structure.md`, `quality-guidelines.md`, `error-handling.md`, `logging-guidelines.md`, `.trellis/spec/guides/index.md`.
