# Refactor notification user bot PK invitation command handlers

## Goal

Reduce `app/domains/notifications/user_bot_service.py` mixed responsibilities by moving the user PK invitation text command handlers into a focused notification domain service while preserving legacy command names and runtime monkeypatch compatibility.

## Requirements

* Extract these text command handlers from `user_bot_service.py` into a new domain-local service module:
  * `cmd_pk_invite`
  * `cmd_pk_accept`
  * `cmd_pk_reject`
* Keep legacy wrapper functions with the same names and signatures in `user_bot_service.py`.
* Wire dependency providers from `user_bot_service.py` using lambdas that read legacy globals at call time.
* Preserve Telegram entity target resolution, Emby username fallback, PK invitation DAO calls, message text, inline keyboard callback payloads, logger behavior, and `safe_error_message` use.
* Add boundary tests that call through `user_bot_service.<legacy_function>` and monkeypatch legacy globals.

## Acceptance Criteria

* [ ] `user_bot_service.cmd_pk_invite` delegates to the new service and preserves unbound, numeric validation, mention resolution, self-PK prevention, invite creation, message send, and invite message ID save behavior.
* [ ] `user_bot_service.cmd_pk_accept` delegates to the new service and preserves latest pending invite lookup, accept DAO call, result text, and duplicate original-chat notification behavior.
* [ ] `user_bot_service.cmd_pk_reject` delegates to the new service and preserves latest pending invite lookup, status update, challenger notification, and user reply behavior.
* [ ] PK callback handlers and dice PK command remain in `user_bot_service.py` for this slice.
* [ ] Focused tests pass with `uv run pytest`.
* [ ] Changed Python files compile with `uv run python -m compileall`.
* [ ] Full test suite passes before commit.

## Definition of Done

* Code and tests are committed in one work commit.
* Trellis task is archived after the work commit.
* Session journal records the work commit hash.

## Technical Approach

Follow the established user bot command extraction pattern:

* Create `app/domains/notifications/user_bot_pk_invitation_commands_service.py`.
* Give the new service dependency providers for `_get_binding`, `_get_binding_by_emby_id`, `_send`, `point_dao`, `user_bot_dao`, `media_api`, `safe_error_message`, and `logger`.
* Update `user_bot_service.py` imports/provider wiring.
* Replace legacy PK invitation command bodies with thin wrappers.
* Keep `_handle_pk_accept_callback`, `_handle_pk_reject_callback`, and `cmd_pk` unchanged.

## Decision (ADR-lite)

Context: The audit recommends small behavior-preserving slices for large domain files. PK invitation text commands form a cohesive sub-flow but have callback handling and dice PK logic nearby that would enlarge the regression surface if moved together.

Decision: Extract only the text command handlers in this slice, leaving callback and dice PK handlers in place.

Consequences: `user_bot_service.py` shrinks while preserving existing dispatch and callback behavior. The callback handlers remain a clear follow-up slice.

## Out of Scope

* PK accept/reject callback extraction.
* Dice PK command extraction.
* Point DAO/schema changes.
* Telegram dispatcher behavior changes.

## Technical Notes

* Audit source: `docs/架构审计.md` P2 item 5.
* Existing extraction patterns: `user_bot_transfer_commands_service.py`, `user_bot_game_commands_service.py`, `user_bot_scratch_commands_service.py`.
* Backend specs read: `.trellis/spec/backend/index.md`, `directory-structure.md`, `quality-guidelines.md`, `error-handling.md`, `logging-guidelines.md`, `.trellis/spec/guides/index.md`.
