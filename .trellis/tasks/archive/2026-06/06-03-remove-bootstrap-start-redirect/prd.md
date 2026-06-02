# Remove Bootstrap Start Redirect

## Requirement

Remove the pure redirect function `start_bootstrap_services()` because it only calls `get_bootstrap_registry(app, request_port).start_all()` and adds no behavior.

## Scope

- Point lifespan startup directly at `get_bootstrap_registry(...).start_all()`.
- Update lifecycle registry tests to start through the registry directly.
- Keep `stop_bootstrap_services()` because it logs shutdown, stops the registry, and resets bootstrap state.

## Non-goals

- Do not remove configuration or variable accessors.
- Do not change service registration order, shutdown behavior, or registry semantics.
