# Refactor Notification User Bot Password Command Handler

## Goal

Continue the architecture audit P2 domain large-file refactor by extracting the Telegram user bot password command handler from `app/domains/notifications/user_bot_service.py` into a focused domain-local service module.

## Scope

- Extract `cmd_password` behavior into a new `app/domains/notifications/user_bot_*_service.py` module.
- Keep `user_bot_service.py` legacy function name as a thin wrapper so existing callers and monkeypatch-based tests keep working.
- Use dependency providers from `user_bot_service.py` so old globals and monkeypatched names are read at call time.
- Preserve message text, state-machine behavior, Emby-account deletion handling, password validation/authentication/change behavior, init-password persistence, reply markup, and error handling.
- Add focused tests that call through `user_bot_service.cmd_password`.

## Out of Scope

- Do not refactor request, server, library, calendar, point-game, dispatch, callback, or polling behavior in this slice.
- Do not change password strength policy, media API behavior, DAO semantics, Telegram API behavior, or database schema.
- Do not mark the overall architecture audit refactor complete; this is one behavior-preserving slice.

## Verification

- Compile changed Python files with `uv run python -m compileall`.
- Run the new focused test file with `uv run pytest`.
- Run an import check for `user_bot_service` and the new service module through `uv run python`.
- Run the full test suite with `uv run pytest tests/ -v`.
- Run `git diff --check`.
