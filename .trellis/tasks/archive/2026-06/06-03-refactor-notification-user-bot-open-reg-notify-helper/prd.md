# Refactor Notification User Bot Open Registration Notify Helper

## Problem

`app/domains/notifications/user_bot_service.py` remains a large mixed-responsibility domain file. The architecture audit recommends splitting large domain files by behavior-preserving slices.

The open-registration closed notification helper is embedded in the large service file. The file currently also contains an earlier duplicate definition of `_send_open_reg_closed_notify()` that is overwritten by the later definition. The actual runtime behavior is the later helper that sends notification messages through the user bot.

## Scope

Extract the active `_send_open_reg_closed_notify()` implementation into a focused notification-domain module while keeping the legacy `user_bot_service._send_open_reg_closed_notify(reason="")` function as a compatibility wrapper.

## Requirements

- Add a domain-local module for open-registration closed notifications.
- Move the active notification implementation behavior into the new module.
- Preserve the legacy wrapper signature: `_send_open_reg_closed_notify(reason="")`.
- Preserve exact notification message text, reason formatting, and timestamp format.
- Preserve behavior:
  - return early when both user and group notifications are disabled;
  - send to all recorded bot users when user notification is enabled;
  - send to configured allowed groups through the user bot when group notification is enabled;
  - parse allowed groups by Chinese comma replacement and newline splitting;
  - log per-user, user-list, per-group, missing-group-config, and group-list failures with the same messages;
  - swallow notification exceptions without raising to registration flows.
- Configure dependencies through providers so monkeypatching old `user_bot_service` globals still affects the wrapper at call time.
- Remove the earlier overwritten duplicate function from `user_bot_service.py` as dead code.
- Do not change registration quota behavior or command handlers in this slice.
- Add focused boundary tests for disabled notifications, user notifications, group notifications, missing group config logging, and swallowed send failures through the legacy wrapper.

## Verification

- Compile the changed modules and new tests.
- Run the focused new test file.
- Run an import check for the changed notification modules.
- Run the full test suite with `uv run pytest tests/ -v`.
