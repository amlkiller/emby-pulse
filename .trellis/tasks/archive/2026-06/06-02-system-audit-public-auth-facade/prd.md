# System Audit Public Auth Facade Boundary

## Goal

Move `app/domains/system/audit.py` off direct private `app.domains.users.auth` imports and route its admin authorization checks through the users public facade, while preserving existing audit page and API behavior.

## Scope

- Update `app/domains/system/audit.py` to use the users public service facade for admin checks.
- Preserve route URLs, response shapes, redirect behavior, template payloads, JSON response status codes, and audit log/stat/action behavior.
- Add focused tests proving the module does not import private users auth and that representative admin gates still protect downstream side effects.

## Acceptance Criteria

- `app/domains/system/audit.py` has no `from app.domains.users.auth ...` or `import app.domains.users.auth` import.
- The audit page redirects unauthenticated requests before admin checks.
- The audit page redirects non-admin users through the public facade.
- Audit log API rejects non-admin requests with the existing `403` JSON response before DAO reads.
- Audit stats/actions APIs use the public facade and preserve success response shapes for admin requests.
- Focused tests, compile/import checks, private import search, diff check, and full test suite pass.
