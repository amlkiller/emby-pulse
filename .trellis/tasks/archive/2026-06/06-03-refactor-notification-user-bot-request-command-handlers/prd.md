# Refactor Notification User Bot Request Command Handlers

## Goal

Continue the architecture audit P2 domain large-file refactor by extracting Telegram user bot media request command handlers from `app/domains/notifications/user_bot_service.py` into a focused domain-local service module.

## Requirements

* Extract `cmd_request`, `cmd_request_callback`, `_submit_request`, and `cmd_myrequests` behavior into a new notification domain service module.
* Keep `user_bot_service.py` legacy function names as thin wrappers so existing callers and monkeypatch-based tests keep working.
* Use dependency providers from `user_bot_service.py` so old globals and monkeypatched names are read at call time.
* Preserve message text, reply/send behavior, callback acknowledgement, deleted Emby account handling, TMDB calls, media request DAO calls, cost/free display logic, admin notification logic, logger behavior, and error handling.
* Add focused boundary tests that call through `user_bot_service.cmd_request`, `cmd_request_callback`, `_submit_request`, and `cmd_myrequests`.

## Acceptance Criteria

* [ ] Request command implementation logic lives outside `user_bot_service.py`.
* [ ] `user_bot_service.py` still exposes `cmd_request`, `cmd_request_callback`, `_submit_request`, and `cmd_myrequests` with the same signatures.
* [ ] Existing runtime dispatch and callback paths continue to call the legacy wrapper functions.
* [ ] Focused tests cover TMDB unavailable/search result rendering, TV season selection/direct submit, submit success notification gating, request DAO failure, and my-requests rendering.
* [ ] Changed Python files compile with `uv run python -m compileall`.
* [ ] New focused tests pass with `uv run pytest`.
* [ ] Import check for `user_bot_service` and the new service module passes through `uv run python`.
* [ ] Full test suite passes with `uv run pytest tests/ -v`.
* [ ] `git diff --check` is clean.

## Technical Approach

Create `app/domains/notifications/user_bot_request_commands_service.py`. The module will own request search, callback, submit, and request history orchestration, with dependency providers for binding lookup, account validation, unbind, Telegram reply/send/API calls, menu keyboard, TMDB client, proxy helper, media request DAO, portal/public URL helpers, safe error formatting, logger, and lazy admin notification dependencies.

`user_bot_service.py` will configure those providers with lambdas that read legacy globals at call time, then expose the same wrapper functions.

## Out of Scope

* Do not refactor check-in, points balance, ranking, robbery, shop, PK, transfer, redpacket, lottery, scratch, dispatch, polling, or registration behavior.
* Do not change TMDB semantics, media request DAO semantics, notification rule behavior, Telegram API behavior, or database schema.
* Do not mark the overall architecture audit refactor complete; this is one behavior-preserving slice.

## Technical Notes

* Architecture audit source: `docs/架构审计.md`, P2 item 5 recommends small behavior-preserving domain file splits.
* Existing split patterns: `user_bot_shop_commands_service.py`, `user_bot_points_game_commands_service.py`, and `user_bot_service_info_commands_service.py`.
* Backend specs to follow: `.trellis/spec/backend/directory-structure.md` and `.trellis/spec/backend/quality-guidelines.md`.
