# Refactor notification user bot PK callback handlers

## Goal

Reduce `app/domains/notifications/user_bot_service.py` mixed responsibilities by moving PK accept/reject callback handling into a focused notification domain service while preserving legacy helper names and callback dispatch behavior.

## Requirements

* Extract these callback helpers from `user_bot_service.py` into a new domain-local service module:
  * `_handle_pk_accept_callback`
  * `_handle_pk_reject_callback`
* Keep legacy wrapper functions with the same names and signatures in `user_bot_service.py`.
* Wire dependency providers from `user_bot_service.py` using lambdas that read legacy globals at call time.
* Preserve callback query responses, invite validation, expiration handling, dice animation calls, DAO calls, edit/send/delete Telegram side effects, logger messages, sleep timing, and error behavior.
* Add boundary tests that call through `user_bot_service.<legacy_helper>` and monkeypatch legacy globals.

## Acceptance Criteria

* [ ] `_handle_pk_accept_callback` delegates to the new service and preserves unbound, missing invite, wrong target, expired invite, success, tie, and failure behavior where covered by focused tests.
* [ ] `_handle_pk_reject_callback` delegates to the new service and preserves unbound, missing invite, wrong target, status update, edit/send, and delete behavior where covered by focused tests.
* [ ] Telegram callback dispatch still calls the legacy helper names.
* [ ] Focused tests pass with `uv run pytest`.
* [ ] Changed Python files compile with `uv run python -m compileall`.
* [ ] Full test suite passes before commit.

## Definition of Done

* Code and tests are committed in one work commit.
* Trellis task is archived after the work commit.
* Session journal records the work commit hash.

## Technical Approach

Follow the established user bot service extraction pattern:

* Create `app/domains/notifications/user_bot_pk_callback_service.py`.
* Give the new service dependency providers for `_get_binding`, `_tg_api`, `_edit`, `_send`, `point_dao`, `datetime`, `time`, and `logger`.
* Update `user_bot_service.py` imports/provider wiring.
* Replace legacy callback helper bodies with thin wrappers.
* Keep `cmd_pk` and callback dispatcher structure unchanged.

## Decision (ADR-lite)

Context: PK callback handling is a cohesive callback sub-flow and the dispatcher already invokes helper functions by name.

Decision: Extract only the callback helper implementations, retaining legacy wrapper names in the original file.

Consequences: `user_bot_service.py` shrinks further while keeping callback dispatch stable. Dice PK command extraction remains a follow-up slice.

## Out of Scope

* Dice PK command extraction.
* PK invitation text command changes.
* Point DAO/schema changes.
* Telegram dispatcher behavior changes.

## Technical Notes

* Audit source: `docs/架构审计.md` P2 item 5.
* Existing extraction patterns: `user_bot_pk_invitation_commands_service.py`, `user_bot_scratch_commands_service.py`.
* Backend specs read: `.trellis/spec/backend/index.md`, `directory-structure.md`, `quality-guidelines.md`, `error-handling.md`, `logging-guidelines.md`, `.trellis/spec/guides/index.md`.
