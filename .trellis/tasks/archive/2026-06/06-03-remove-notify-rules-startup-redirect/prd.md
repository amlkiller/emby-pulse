# Remove Notify Rules Startup Redirect

## Requirement

Remove the pure redirect from `start_notify_rules_services()` to `_ensure_bot_notify_mutes_table()` while keeping the public startup function.

## Scope

- Move the `_ensure_bot_notify_mutes_table()` implementation into `start_notify_rules_services()`.
- Keep existing callers using the public startup function.
- Preserve bot notify mute table initialization behavior and error output.

## Non-goals

- Do not remove configuration or variable accessors.
- Do not change notification startup ordering, route behavior, DAO behavior, or error handling.
