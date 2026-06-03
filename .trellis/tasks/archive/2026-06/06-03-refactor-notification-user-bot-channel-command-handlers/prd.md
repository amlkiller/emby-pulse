# Refactor Notification User Bot Channel Command Handlers

## Goal

Continue the architecture audit P2 domain large-file refactor by extracting Telegram user bot channel-binding command handlers from `app/domains/notifications/user_bot_service.py` into a focused domain-local service module.

## Scope

- Extract `cmd_bind_channel` and `cmd_unbind_channel` behavior into a new `app/domains/notifications/user_bot_*_service.py` module.
- Keep `user_bot_service.py` legacy function names as thin wrappers so existing callers and monkeypatch-based tests keep working.
- Use dependency providers from `user_bot_service.py` so old globals and monkeypatched names are read at call time.
- Preserve message text, return values, binding checks, channel ID parsing, DAO wrapper calls, and error handling.
- Add focused tests that call through `user_bot_service.cmd_bind_channel` and `cmd_unbind_channel`.

## Out of Scope

- Do not refactor profile, password, request, server, library, calendar, point-game, dispatch, or polling behavior in this slice.
- Do not change Telegram callback behavior, database schema, or channel binding persistence semantics.
- Do not mark the overall architecture audit refactor complete; this is one behavior-preserving slice.

## Verification

- Compile changed Python files with `uv run python -m compileall`.
- Run the new focused test file with `uv run pytest`.
- Run an import check for `user_bot_service` and the new service module through `uv run python`.
- Run the full test suite with `uv run pytest tests/ -v`.
- Run `git diff --check`.
