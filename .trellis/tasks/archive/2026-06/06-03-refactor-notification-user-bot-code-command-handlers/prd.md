# Refactor Notification User Bot Code Command Handlers

## Problem

`app/domains/notifications/user_bot_service.py` remains a large mixed-responsibility domain file. The architecture audit recommends splitting large domain files by behavior-preserving slices.

The user bot command handlers for restriction checks, registration-code verification, invitation-code restore, and renewal-code application are grouped near the registration flow. They can be moved into a focused notification-domain module while keeping the legacy function names available.

## Scope

Extract `cmd_check()`, `cmd_code()`, `_restore_invitation_code()`, and `cmd_renew()` into a focused domain-local service. Keep the same legacy functions in `user_bot_service.py` as compatibility wrappers.

## Requirements

- Add a domain-local module for code/check/renew user bot command handlers.
- Preserve the legacy signatures:
  - `cmd_check(chat_id, tg_user_id)`
  - `cmd_code(chat_id, tg_user_id, args)`
  - `_restore_invitation_code(code)`
  - `cmd_renew(chat_id, tg_user_id, args)`
- Preserve exact message text, reply markup behavior, state mutation, and command branching.
- Preserve `cmd_check` cache-clear and restriction formatting behavior.
- Preserve `cmd_code` invitation lookup, binding guard, max-use guard, `_user_state` payload, and safe error handling.
- Preserve `_restore_invitation_code` swallowing behavior.
- Preserve `cmd_renew` binding guard, renewal error handling, permanent-code display, success text, and safe error handling.
- Configure dependencies through providers so monkeypatching old `user_bot_service` globals still affects wrappers at call time.
- Do not move `_do_code_register()` or registration account creation in this slice.
- Add focused boundary tests through the legacy wrappers.

## Verification

- Compile the changed modules and new tests.
- Run the focused new test file.
- Run an import check for the changed notification modules.
- Run the full test suite with `uv run pytest tests/ -v`.
