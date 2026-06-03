# Refactor notification user bot dice PK command handler

## Goal

Reduce `app/domains/notifications/user_bot_service.py` mixed responsibilities by moving the direct dice PK command implementation into a focused notification domain service while preserving the legacy command entrypoint and dispatcher behavior.

## Requirements

* Extract `cmd_pk` from `user_bot_service.py` into a new domain-local command service module.
* Keep a legacy `cmd_pk(chat_id, tg_user_id, text, is_group=False, tg_name="", user_msg_id=None)` wrapper in `user_bot_service.py`.
* Wire dependency providers from `user_bot_service.py` using lambdas that read legacy globals at call time.
* Preserve binding validation, command usage text, amount parsing, config validation, daily limit checks, balance checks, Telegram dice calls, dice fallback randomization, point DAO calls, group cleanup scheduling, logger messages, sleep timing, and error behavior.
* Add boundary tests that call through `user_bot_service.cmd_pk` and monkeypatch legacy globals.

## Acceptance Criteria

* [ ] `cmd_pk` delegates to the new service and preserves unbound, usage, invalid amount, disabled config, limit, balance, win, loss, tie, dice failure, and exception behavior where covered by focused tests.
* [ ] Group cleanup still includes the user command message, start message, both dice messages, and result message when available.
* [ ] Telegram command dispatch still calls the legacy `cmd_pk` name.
* [ ] Focused tests pass with `uv run pytest`.
* [ ] Changed Python files compile with `uv run python -m compileall`.
* [ ] Full test suite passes before commit.

## Definition of Done

* Code and tests are committed in one work commit.
* Trellis task is archived after the work commit.
* Session journal records the work commit hash.

## Technical Approach

Follow the established user bot service extraction pattern:

* Create `app/domains/notifications/user_bot_dice_pk_commands_service.py`.
* Give the new service dependency providers for `_get_binding`, `_send`, `_tg_api`, `_delete_messages_later`, `point_dao`, `random`, `time.sleep`, and `logger`.
* Update `user_bot_service.py` imports/provider wiring.
* Replace the legacy `cmd_pk` body with a thin wrapper.
* Keep dispatcher structure and command matching unchanged.

## Decision (ADR-lite)

Context: `cmd_pk` is a cohesive direct dice game command and still lives in the large user bot compatibility module after the invitation/callback PK flows were extracted.

Decision: Extract only the direct dice PK command implementation, retaining the legacy wrapper name in the original file.

Consequences: `user_bot_service.py` shrinks further while existing command dispatch and test monkeypatch surfaces remain stable. Broader user bot dispatcher splitting remains a follow-up slice.

## Out of Scope

* User-to-user PK invitation command changes.
* PK callback handler changes.
* Point DAO/schema changes.
* Telegram dispatcher behavior changes.
* Reworking dice game odds or message copy.

## Technical Notes

* Audit source: `docs/架构审计.md` P2 item 5.
* Existing extraction patterns: `user_bot_pk_invitation_commands_service.py`, `user_bot_pk_callback_service.py`, `user_bot_transfer_commands_service.py`.
* Relevant specs: `.trellis/spec/backend/index.md`, `directory-structure.md`, `quality-guidelines.md`, `error-handling.md`, `logging-guidelines.md`, `.trellis/spec/guides/index.md`.
