# Refactor Notification User Bot Points Game Command Handlers

## Goal

Continue the architecture audit P2 domain large-file refactor by extracting the Telegram user bot points game command handlers for ranking and robbery from `app/domains/notifications/user_bot_service.py` into a focused domain-local service module.

## Requirements

* Extract `cmd_rank` and `cmd_rob` behavior into a new notification domain service module.
* Keep `user_bot_service.py` legacy function names as thin wrappers so existing callers and monkeypatch-based tests keep working.
* Use dependency providers from `user_bot_service.py` so old globals and monkeypatched names are read at call time.
* Preserve message text, Telegram reply behavior, Emby user lookup, binding lookup, point DAO calls, target resolution, logger behavior, and error handling.
* Add focused boundary tests that call through `user_bot_service.cmd_rank` and `cmd_rob`.

## Acceptance Criteria

* [ ] `cmd_rank` and `cmd_rob` implementation logic lives outside `user_bot_service.py`.
* [ ] `user_bot_service.py` still exposes `cmd_rank` and `cmd_rob` with the same signatures.
* [ ] Existing runtime dispatch paths continue to call the legacy wrapper functions.
* [ ] Focused tests cover ranking output, unbound robbery, mention target resolution, and safe error handling.
* [ ] Changed Python files compile with `uv run python -m compileall`.
* [ ] New focused tests pass with `uv run pytest`.
* [ ] Import check for `user_bot_service` and the new service module passes through `uv run python`.
* [ ] Full test suite passes with `uv run pytest tests/ -v`.
* [ ] `git diff --check` is clean.

## Technical Approach

Create a `user_bot_service_points_game_commands_service.py` module next to the existing notification user bot command service modules. The new module will own ranking and robbery command implementations, with dependency providers for binding lookup, Telegram send, point DAO, user bot DAO, media API, logger, and safe error formatting.

`user_bot_service.py` will configure those providers with lambdas that read legacy globals at call time, then expose the same `cmd_rank` and `cmd_rob` wrappers.

## Out of Scope

* Do not refactor check-in, points balance, PK, transfer, redpacket, lottery, scratch, shop, request, callback dispatch, polling, or registration behavior.
* Do not change point DAO semantics, Telegram API behavior, Emby API behavior, or database schema.
* Do not mark the overall architecture audit refactor complete; this is one behavior-preserving slice.

## Technical Notes

* Architecture audit source: `docs/架构审计.md`, P2 item 5 recommends small behavior-preserving domain file splits.
* Existing split pattern: `app/domains/notifications/user_bot_service_info_commands_service.py`.
* Backend specs to follow: `.trellis/spec/backend/directory-structure.md` and `.trellis/spec/backend/quality-guidelines.md`.
