# Refactor Notification User Bot Point Command Handlers

## Goal

Continue the architecture audit P2 domain large-file refactor by extracting the Telegram user bot point-related command handlers from `app/domains/notifications/user_bot_service.py` into a focused domain-local service module.

## Scope

- Extract `cmd_checkin` and `cmd_points` behavior into a new `app/domains/notifications/user_bot_*_service.py` module.
- Keep `user_bot_service.py` legacy function names as thin wrappers so existing callers and monkeypatch-based tests keep working.
- Use dependency providers from `user_bot_service.py` so old globals and monkeypatched names are read at call time.
- Preserve message text, return values, group/private behavior, cleanup scheduling, DAO calls, and error handling.
- Add focused tests that call through `user_bot_service.cmd_checkin` / `cmd_points`.

## Out of Scope

- Do not refactor registration flows, game commands, rank commands, routing dispatch, or Telegram polling in this slice.
- Do not change database schema, point DAO semantics, or Telegram API behavior.
- Do not mark the overall architecture audit refactor complete; this is one behavior-preserving slice.

## Verification

- Compile changed Python files with `uv run python -m compileall`.
- Run the new focused test file with `uv run pytest`.
- Run the full test suite with `uv run pytest tests/ -v`.
- Run an import check for `user_bot_service` and the new service module through `uv run python`.
- Run `git diff --check`.
