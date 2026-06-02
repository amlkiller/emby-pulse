# System Tools Public Auth Facade Boundary

## Goal

Move `app/domains/system/system_tools.py` off direct private `app.domains.users.auth` imports and route its route-level admin authorization checks through the users public facade, while preserving existing system diagnostics, log, debug, restart, and weather API behavior.

## Scope

- Update `app/domains/system/system_tools.py` to use the users public service facade for admin checks.
- Preserve route URLs, response shapes, messages, weather cache behavior, log/debug behavior, restart behavior, and diagnostics behavior.
- Add focused tests proving the module does not import private users auth and that representative admin gates still protect downstream side effects.

## Acceptance Criteria

- `app/domains/system/system_tools.py` has no `from app.domains.users.auth ...` or `import app.domains.users.auth` import.
- Performance status rejects non-admin requests before collecting expensive/process/cache data.
- Network check still rejects unauthenticated requests before admin checks.
- Log/debug/weather routes use the public facade and preserve representative success/error response shapes.
- Focused tests, compile/import checks, private import search, diff check, and full test suite pass.
