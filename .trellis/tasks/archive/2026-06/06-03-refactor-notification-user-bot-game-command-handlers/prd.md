# Refactor notification user bot game command handlers

## Goal

Reduce `app/domains/notifications/user_bot_service.py` mixed responsibilities by moving the standalone user bot game command handlers into a focused notification domain service while preserving legacy command function names and runtime monkeypatch compatibility.

## Requirements

* Extract `cmd_grab` and `cmd_lottery` implementation from `user_bot_service.py` into a new domain-local service module.
* Keep `cmd_scratch` as a legacy wrapper in `user_bot_service.py`; the scratch callback helpers remain in the original file for this slice.
* Wire dependency providers from `user_bot_service.py` using lambdas that read legacy globals at call time.
* Preserve public function signatures, Telegram message text, DAO calls, logger behavior, and group cleanup timing.
* Add boundary tests that call through `user_bot_service.<legacy_function>` and monkeypatch legacy globals.

## Acceptance Criteria

* [ ] `user_bot_service.cmd_grab` delegates to the new service and still handles unbound users, successful grabs, last-red-packet notifications, and group cleanup.
* [ ] `user_bot_service.cmd_lottery` delegates to the new service and still handles disabled lottery, my-ticket view, pool view, ticket purchase validation, and group cleanup.
* [ ] `user_bot_service.cmd_scratch` continues to work through the original scratch implementation and callback helpers are not moved in this slice.
* [ ] Focused tests pass with `uv run pytest`.
* [ ] Changed Python files compile with `uv run python -m compileall`.
* [ ] Full test suite passes before commit.

## Definition of Done

* Code and tests are committed in one work commit.
* Trellis task is archived after the work commit.
* Session journal records the work commit hash.

## Technical Approach

Follow the established user bot command extraction pattern:

* Create `app/domains/notifications/user_bot_game_commands_service.py`.
* Give the new service dependency providers for `_get_binding`, `_send`, `_delete_messages_later`, `point_dao`, `media_api`, `logger`, `datetime`, and a notification fallback.
* Update `user_bot_service.py` imports/provider wiring.
* Replace legacy `cmd_grab` and `cmd_lottery` bodies with thin wrappers.
* Leave `_cmd_scratch_impl`, `_handle_scratch`, `_update_scratch_message`, and `_scratch_draw_result` in `user_bot_service.py`.

## Decision (ADR-lite)

Context: The audit recommends behavior-preserving small slices for large domain files. `cmd_grab` and `cmd_lottery` are cohesive point-game commands and already depend mainly on points DAO, send helpers, and cleanup helpers.

Decision: Extract the command bodies into a focused service while preserving legacy wrappers and late-bound dependency providers.

Consequences: `user_bot_service.py` shrinks without forcing a broader scratch callback or PK refactor. Scratch remains a known follow-up because its command entry and callback helpers are tightly coupled.

## Out of Scope

* PK invite/accept/reject/callback flows.
* Scratch callback helper extraction.
* Point DAO/schema changes.
* Telegram dispatcher behavior changes.

## Technical Notes

* Audit source: `docs/架构审计.md` P2 item 5.
* Existing extraction patterns: `user_bot_points_game_commands_service.py`, `user_bot_transfer_commands_service.py`.
* Backend specs read: `.trellis/spec/backend/index.md`, `directory-structure.md`, `quality-guidelines.md`, `error-handling.md`, `logging-guidelines.md`, `.trellis/spec/guides/index.md`.
