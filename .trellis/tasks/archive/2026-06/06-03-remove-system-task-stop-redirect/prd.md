# Remove System Task Stop Redirect

## Requirement

Remove the pure redirect function `stop_system_task_services()` because it only calls `stop_task_poller()` and adds no behavior.

## Scope

- Point bootstrap shutdown registration directly at `stop_task_poller()`.
- Update lifecycle tests to patch and call the real stop implementation.
- Keep `start_system_task_services()` because it initializes task defaults and starts the poller.

## Non-goals

- Do not remove configuration or variable accessors.
- Do not change task polling behavior, startup ordering, shutdown ordering, or route behavior.
