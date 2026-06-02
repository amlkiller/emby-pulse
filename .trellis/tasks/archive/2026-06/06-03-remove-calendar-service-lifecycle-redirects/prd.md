# Remove Calendar Service Lifecycle Redirects

## Requirement

Remove the pure redirect functions `start_calendar_service()` and `stop_calendar_service()` because they only call `calendar_service.start()` and `calendar_service.stop()`.

## Scope

- Point bootstrap lifecycle registration directly at `calendar_service.start` and `calendar_service.stop`.
- Update lifecycle registry tests to patch the real service methods.
- Keep `CalendarService.start()` and `CalendarService.stop()` because they are the service object's public lifecycle API.

## Non-goals

- Do not remove configuration or variable accessors.
- Do not change calendar sync behavior, route behavior, cache behavior, or shutdown ordering.
