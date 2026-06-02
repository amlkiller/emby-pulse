# System Tasks Public Auth Facade Boundary

## Goal

Move `app/domains/system/tasks.py` off direct private `app.domains.users.auth` imports and route its route-level admin authorization checks through the users public facade, while preserving existing task API behavior and background service lifecycle behavior.

## Scope

- Update `app/domains/system/tasks.py` to use the users public service facade for admin checks.
- Preserve route URLs, response shapes, messages, Emby task calls, translation persistence behavior, config behavior, and poller lifecycle behavior.
- Add focused tests proving the module does not import private users auth and that representative admin gates still protect downstream side effects.

## Acceptance Criteria

- `app/domains/system/tasks.py` has no `from app.domains.users.auth ...` or `import app.domains.users.auth` import.
- Non-admin task config reads return the existing permission error before reading config state.
- Admin task config reads use the public facade and preserve the success response shape.
- Non-admin task translation writes return the existing permission error before saving or deleting translations.
- Admin task start requests use the public facade and preserve the media server call/response behavior.
- Focused tests, compile/import checks, private import search, diff check, and full test suite pass.
