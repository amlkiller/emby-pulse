# Remove Calendar Service Internal Lifecycle Redirects

## Requirement

Remove the pure redirects from `CalendarService.start()` and `CalendarService.stop()` to private lifecycle helpers.

## Scope

- Move `_start_background_sync()` logic into `CalendarService.start()`.
- Move `_stop_background_sync()` logic into `CalendarService.stop()`.
- Keep bootstrap using the public `calendar_service.start` and `calendar_service.stop` lifecycle methods.

## Non-goals

- Do not remove configuration or variable accessors.
- Do not change calendar sync behavior, cache behavior, thread timing, or shutdown semantics.
