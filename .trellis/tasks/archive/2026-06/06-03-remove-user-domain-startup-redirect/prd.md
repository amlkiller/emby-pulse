# Remove User Domain Startup Redirect

## Requirement

Remove the pure redirect function `start_user_domain_services()` because it only calls `migrate_admin_disabled()` and adds no behavior.

## Scope

- Point bootstrap startup registration directly at `migrate_admin_disabled()`.
- Update lifecycle registry tests to patch the real startup implementation.
- Keep `migrate_admin_disabled()` because it owns the actual migration behavior.

## Non-goals

- Do not remove configuration or variable accessors.
- Do not change user migration behavior, route behavior, startup ordering, or DAO calls.
