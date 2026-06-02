# Remove Auth Domain Stop Redirect

## Requirement

Remove the pure redirect from `stop_auth_domain_services()` to `_stop_lock_cleanup()` while keeping the public auth-domain shutdown function.

## Scope

- Move the `_stop_lock_cleanup()` implementation into `stop_auth_domain_services()`.
- Keep bootstrap registered to the public auth-domain lifecycle function.
- Preserve login lock cleanup shutdown behavior.

## Non-goals

- Do not remove configuration or variable accessors.
- Do not change auth startup behavior, local user setup, route behavior, or lock cleanup timing.
