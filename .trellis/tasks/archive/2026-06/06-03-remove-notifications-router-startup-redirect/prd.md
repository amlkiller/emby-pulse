# Remove Notifications Router Startup Redirect

## Requirement

Remove the pure redirect from `start_notifications_router_services()` to `_ensure_table()` while keeping the public bootstrap startup function.

## Scope

- Move the `_ensure_table()` implementation into `start_notifications_router_services()`.
- Keep bootstrap registered to the public startup function.
- Preserve notification table initialization behavior and error logging.

## Non-goals

- Do not remove configuration or variable accessors.
- Do not change notification route behavior, DAO behavior, startup ordering, or error handling.
