# System Clients Public Auth Facade Boundary

## Goal

Move `app/domains/system/clients.py` off direct private `app.domains.users.auth` imports and route its route-level admin authorization checks through the users public facade, while preserving existing client blacklist/whitelist/data/block behavior.

## Scope

- Update `app/domains/system/clients.py` to use the users public service facade for admin checks.
- Preserve route URLs, response shapes, messages, client DAO behavior, media server calls, audit logging behavior, and cache/blocking behavior.
- Add focused tests proving the module does not import private users auth and that representative admin gates still protect downstream side effects.

## Acceptance Criteria

- `app/domains/system/clients.py` has no `from app.domains.users.auth ...` or `import app.domains.users.auth` import.
- Non-admin blacklist reads return the existing permission error before DAO reads.
- Admin blacklist reads use the public facade and preserve the success response shape.
- Non-admin blacklist writes return the existing permission error before DAO/audit side effects.
- Admin client data reads use the public facade before blacklist scan/cache/media work.
- Non-admin execute-block requests return the existing permission error before block/audit side effects.
- Focused tests, compile/import checks, private import search, diff check, and full test suite pass.
