# System DB Tools Public Auth Facade Boundary

## Goal

Move `app/domains/system/db_tools.py` off direct private `app.domains.users.auth` imports and route its route-level admin authorization checks through the users public facade, while preserving existing database management API behavior.

## Scope

- Update `app/domains/system/db_tools.py` to use the users public service facade for admin checks.
- Preserve route URLs, response shapes, JSON status codes, migration/repair/backup behavior, audit logging behavior, and path validation behavior.
- Add focused tests proving the module does not import private users auth and that representative admin gates still protect downstream side effects.

## Acceptance Criteria

- `app/domains/system/db_tools.py` has no `from app.domains.users.auth ...` or `import app.domains.users.auth` import.
- Non-admin health checks return the existing `403` JSON response before health check side effects.
- Admin health checks use the public facade and preserve the health response.
- Non-admin repair/backup-style write operations return the existing `403` JSON response before audit or database side effects.
- Admin backup requests use the public facade and preserve the success payload shape.
- Focused tests, compile/import checks, private import search, diff check, and full test suite pass.
