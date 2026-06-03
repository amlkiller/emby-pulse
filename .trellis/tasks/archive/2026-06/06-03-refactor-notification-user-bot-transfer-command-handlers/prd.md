# Refactor Notification User Bot Transfer Command Handlers

## Goal

Continue the architecture audit P2 domain large-file refactor by extracting Telegram user bot point transfer and red packet command handlers from `app/domains/notifications/user_bot_service.py` into a focused domain-local service module.

## Requirements

* Extract `cmd_transfer` and `cmd_redpacket` behavior into a new notification domain service module.
* Keep `user_bot_service.py` legacy function names as thin wrappers so existing callers and monkeypatch-based tests keep working.
* Use dependency providers from `user_bot_service.py` so old globals and monkeypatched names are read at call time.
* Preserve message text, send behavior, binding lookup, target resolution from Telegram entities/usernames/Emby usernames, point DAO calls, red packet deletion scheduling, logger behavior, and safe error handling.
* Add focused boundary tests that call through `user_bot_service.cmd_transfer` and `cmd_redpacket`.

## Acceptance Criteria

* [ ] Transfer and red packet command implementation logic lives outside `user_bot_service.py`.
* [ ] `user_bot_service.py` still exposes `cmd_transfer` and `cmd_redpacket` with the same signatures.
* [ ] Existing runtime dispatch paths continue to call the legacy wrapper functions.
* [ ] Focused tests cover transfer target resolution, transfer self-check, transfer success/failure messages, red packet success scheduling, and masked exception handling.
* [ ] Changed Python files compile with `uv run python -m compileall`.
* [ ] New focused tests pass with `uv run pytest`.
* [ ] Import check for `user_bot_service` and the new service module passes through `uv run python`.
* [ ] Full test suite passes with `uv run pytest tests/ -v`.
* [ ] `git diff --check` is clean.

## Technical Approach

Create `app/domains/notifications/user_bot_transfer_commands_service.py`. The module will own transfer and red packet orchestration, with dependency providers for binding lookup, Telegram send, delayed message cleanup, user bot DAO, point DAO, media API, safe error formatting, and logger.

`user_bot_service.py` will configure those providers with lambdas that read legacy globals at call time, then expose the same wrapper functions.

## Out of Scope

* Do not refactor check-in, points balance, ranking, robbery, shop, request, PK invite/accept/reject, dice PK, grab, lottery, scratch, dispatch, polling, or registration behavior.
* Do not change point DAO semantics, Telegram API behavior, Emby API behavior, or database schema.
* Do not mark the overall architecture audit refactor complete; this is one behavior-preserving slice.

## Technical Notes

* Architecture audit source: `docs/架构审计.md`, P2 item 5 recommends small behavior-preserving domain file splits.
* Existing split patterns: `user_bot_request_commands_service.py`, `user_bot_shop_commands_service.py`, and `user_bot_points_game_commands_service.py`.
* Backend specs to follow: `.trellis/spec/backend/directory-structure.md` and `.trellis/spec/backend/quality-guidelines.md`.
