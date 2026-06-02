# Remove Calendar Notify Stop Redirect

## Requirement

Remove the pure redirect function `stop_calendar_notify_services()` because it only calls `calendar_notify_service.stop()` and adds no behavior.

## Scope

- Point bootstrap shutdown registration directly at `calendar_notify_service.stop`.
- Update lifecycle tests to call or patch the real stop method.
- Keep `start_calendar_notify_services()` because it ensures the table and starts the service.

## Non-goals

- Do not remove configuration or variable accessors.
- Do not change calendar notification startup, shutdown behavior, route behavior, or schema setup.
