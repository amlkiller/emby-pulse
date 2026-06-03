# Refactor notification user bot scratch command handlers

## Goal

Reduce `app/domains/notifications/user_bot_service.py` mixed responsibilities by moving scratch card command and callback handling into a focused notification domain service while preserving legacy function names and runtime monkeypatch compatibility.

## Requirements

* Extract scratch card user bot handling from `user_bot_service.py` into a new domain-local service module:
  * `cmd_scratch`
  * `_cmd_scratch_impl`
  * `_handle_scratch`
  * `_update_scratch_message`
  * `_scratch_draw_result`
* Keep legacy wrapper functions with the same names and signatures in `user_bot_service.py`.
* Wire dependency providers from `user_bot_service.py` using lambdas that read legacy globals at call time.
* Preserve Telegram messages, inline keyboard callback payloads, DAO calls, random prize generation behavior, media admin check behavior, `_tg_api` edit behavior, logger messages, and delayed deletion timing.
* Add boundary tests that call through `user_bot_service.<legacy_function>` and monkeypatch legacy globals.

## Acceptance Criteria

* [ ] `user_bot_service.cmd_scratch` delegates to the new service and preserves disabled, info, create, admin-only, and group cleanup behavior.
* [ ] `user_bot_service._handle_scratch` delegates to the new service and preserves scratch slot update, message markup refresh, last-slot draw, and error handling behavior.
* [ ] `user_bot_service._update_scratch_message` delegates to the new service and preserves `editMessageReplyMarkup` payloads.
* [ ] `user_bot_service._scratch_draw_result` delegates to the new service and preserves summary text and delayed origin-message deletion.
* [ ] Focused tests pass with `uv run pytest`.
* [ ] Changed Python files compile with `uv run python -m compileall`.
* [ ] Full test suite passes before commit.

## Definition of Done

* Code and tests are committed in one work commit.
* Trellis task is archived after the work commit.
* Session journal records the work commit hash.

## Technical Approach

Follow the established user bot command extraction pattern:

* Create `app/domains/notifications/user_bot_scratch_commands_service.py`.
* Give the new service dependency providers for `_get_binding`, `_send`, `_delete_messages_later`, `_tg_api`, `point_dao`, `media_api`, `random`, and `logger`.
* Update `user_bot_service.py` imports/provider wiring.
* Replace legacy scratch functions with thin wrappers.
* Keep Telegram callback dispatch paths unchanged; they continue to call the legacy wrapper names.

## Decision (ADR-lite)

Context: The audit recommends small behavior-preserving slices for large domain files. Scratch card command handling is a cohesive sub-flow with command entry, callback slot handling, message markup refresh, and draw summary.

Decision: Extract the complete scratch handling sub-flow into a focused service, while retaining legacy wrappers in `user_bot_service.py`.

Consequences: `user_bot_service.py` shrinks further without changing dispatcher structure or point DAO/schema contracts. The new service remains compatible with current tests and callers that patch old module globals.

## Out of Scope

* PK invite/accept/reject/callback flows.
* Lottery draw scheduler and `do_lottery_draw`.
* Point DAO/schema changes.
* Telegram dispatcher behavior changes.

## Technical Notes

* Audit source: `docs/架构审计.md` P2 item 5.
* Existing extraction patterns: `user_bot_game_commands_service.py`, `user_bot_transfer_commands_service.py`.
* Backend specs read: `.trellis/spec/backend/index.md`, `directory-structure.md`, `quality-guidelines.md`, `error-handling.md`, `logging-guidelines.md`, `.trellis/spec/guides/index.md`.
