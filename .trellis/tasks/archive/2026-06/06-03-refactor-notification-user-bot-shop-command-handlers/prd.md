# Refactor Notification User Bot Shop Command Handlers

## Goal

Continue the architecture audit P2 domain large-file refactor by extracting Telegram user bot shop and redeem command handlers from `app/domains/notifications/user_bot_service.py` into a focused domain-local service module.

## Requirements

* Extract `cmd_shop` and `cmd_redeem_callback` behavior into a new notification domain service module.
* Keep `user_bot_service.py` legacy function names as thin wrappers so existing callers and monkeypatch-based tests keep working.
* Use dependency providers from `user_bot_service.py` so old globals and monkeypatched names are read at call time.
* Preserve message text, reply/send behavior, callback acknowledgement, deleted Emby account handling, point DAO calls, Emby enable calls, admin notifications, logger behavior, and error handling.
* Add focused boundary tests that call through `user_bot_service.cmd_shop` and `cmd_redeem_callback`.

## Acceptance Criteria

* [ ] `cmd_shop` and `cmd_redeem_callback` implementation logic lives outside `user_bot_service.py`.
* [ ] `user_bot_service.py` still exposes `cmd_shop` and `cmd_redeem_callback` with the same signatures.
* [ ] Existing runtime dispatch and callback paths continue to call the legacy wrapper functions.
* [ ] Focused tests cover shop item rendering, unbound/deleted account paths, redeem success, redeem business failure, and masked exception handling.
* [ ] Changed Python files compile with `uv run python -m compileall`.
* [ ] New focused tests pass with `uv run pytest`.
* [ ] Import check for `user_bot_service` and the new service module passes through `uv run python`.
* [ ] Full test suite passes with `uv run pytest tests/ -v`.
* [ ] `git diff --check` is clean.

## Technical Approach

Create `app/domains/notifications/user_bot_shop_commands_service.py`. The module will own shop and redemption orchestration, with dependency providers for binding lookup, account validation, unbind, Telegram reply/send/API calls, menu keyboard, point DAO, media API, safe error formatting, logger, and lazy notification dependencies.

`user_bot_service.py` will configure those providers with lambdas that read legacy globals at call time, then expose the same `cmd_shop` and `cmd_redeem_callback` wrappers.

## Out of Scope

* Do not refactor check-in, points balance, ranking, robbery, PK, transfer, redpacket, lottery, scratch, request, callback dispatch, polling, or registration behavior.
* Do not change point DAO semantics, Telegram API behavior, Emby API behavior, notification rule behavior, or database schema.
* Do not mark the overall architecture audit refactor complete; this is one behavior-preserving slice.

## Technical Notes

* Architecture audit source: `docs/架构审计.md`, P2 item 5 recommends small behavior-preserving domain file splits.
* Existing split patterns: `user_bot_service_info_commands_service.py` and `user_bot_points_game_commands_service.py`.
* Backend specs to follow: `.trellis/spec/backend/directory-structure.md` and `.trellis/spec/backend/quality-guidelines.md`.
