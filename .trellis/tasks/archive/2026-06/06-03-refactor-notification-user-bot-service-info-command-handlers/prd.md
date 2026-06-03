# Refactor Notification User Bot Service Info Command Handlers

## Goal

Continue the architecture audit P2 domain large-file refactor by extracting Telegram user bot service information command handlers from `app/domains/notifications/user_bot_service.py` into a focused domain-local service module.

## Scope

- Extract `cmd_server`, `cmd_library`, and `cmd_calendar` behavior into a new `app/domains/notifications/user_bot_*_service.py` module.
- Keep `user_bot_service.py` legacy function names as thin wrappers so existing callers and monkeypatch-based tests keep working.
- Use dependency providers from `user_bot_service.py` so old globals and monkeypatched names are read at call time.
- Preserve message text, reply/edit behavior, account deletion handling, Emby API calls, calendar notify calls, logger behavior, and error handling.
- Add focused tests that call through `user_bot_service.cmd_server`, `cmd_library`, and `cmd_calendar`.

## Out of Scope

- Do not refactor request, point-game, dispatch, callback, polling, or registration behavior in this slice.
- Do not change media API semantics, calendar notify behavior, Telegram API behavior, or database schema.
- Do not mark the overall architecture audit refactor complete; this is one behavior-preserving slice.

## Verification

- Compile changed Python files with `uv run python -m compileall`.
- Run the new focused test file with `uv run pytest`.
- Run an import check for `user_bot_service` and the new service module through `uv run python`.
- Run the full test suite with `uv run pytest tests/ -v`.
- Run `git diff --check`.
