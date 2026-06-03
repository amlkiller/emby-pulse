# Refactor Notification User Bot Basic Command Handlers

## Problem

`app/domains/notifications/user_bot_service.py` remains a large mixed-responsibility domain file. The architecture audit recommends splitting large domain files by behavior-preserving slices.

The basic user bot command handlers for `/start`, `/help`, `/bind`, and `/register` are grouped near the top of the large service file. They are a coherent command slice and can be moved into a focused notification-domain module while keeping the legacy function names available.

## Scope

Extract `cmd_start()`, `cmd_help()`, `cmd_bind()`, and `cmd_register()` into a focused domain-local service. Keep the same legacy functions in `user_bot_service.py` as compatibility wrappers.

## Requirements

- Add a domain-local module for basic user bot command handlers.
- Preserve the legacy signatures:
  - `cmd_start(chat_id, tg_user_id, tg_name)`
  - `cmd_help(chat_id, tg_user_id)`
  - `cmd_bind(chat_id, tg_user_id, args, tg_username="", tg_display_name="")`
  - `cmd_register(chat_id, tg_user_id, tg_name)`
- Preserve exact message text, reply markup behavior, and command branching.
- Preserve `/bind` media authentication behavior, success binding call, and safe error handling.
- Preserve `/register` open-registration, existing-binding, blacklist, and `_user_state` mutation behavior.
- Configure dependencies through providers so monkeypatching old `user_bot_service` globals still affects wrappers at call time.
- Do not move polling dispatch, registration creation flows, quota logic, or callback handlers in this slice.
- Add focused boundary tests through the legacy wrappers.

## Verification

- Compile the changed modules and new tests.
- Run the focused new test file.
- Run an import check for the changed notification modules.
- Run the full test suite with `uv run pytest tests/ -v`.
