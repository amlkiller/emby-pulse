# Remove Notification Message Log Redirect

## Goal

Remove the `log_msg()` helper in `app/domains/notifications/messages.py` because it only forwards to `print(..., flush=True)`.

## Scope

- Replace internal `log_msg(...)` calls with direct `print(..., flush=True)` calls.
- Delete the `log_msg()` helper.
- Preserve all message text and flush behavior.
- Do not change notification message routing, DAO calls, public API behavior, or configuration access.

## Acceptance Criteria

- No `log_msg` definition or call remains.
- The changed module compiles and imports.
- Focused notification message tests and the full test suite pass.
