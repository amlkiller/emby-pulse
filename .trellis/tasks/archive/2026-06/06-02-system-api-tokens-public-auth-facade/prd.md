# System API Tokens Public Auth Facade Boundary

## Goal

Move `app/domains/system/api_tokens.py` off direct private `app.domains.users.auth` imports and route its admin authorization checks through the users public facade, while preserving existing API token route behavior.

## Scope

- Update `app/domains/system/api_tokens.py` to use the users public service facade for admin checks.
- Preserve route URLs, response shapes, HTTP status codes, token creation/list/delete/verify behavior, and error messages.
- Add focused tests proving the module does not import private users auth and that admin gating still protects token management side effects.

## Acceptance Criteria

- `app/domains/system/api_tokens.py` has no `from app.domains.users.auth ...` or `import app.domains.users.auth` import.
- Token creation still rejects unauthenticated requests before admin checks.
- Token creation rejects non-admin authenticated requests before token/database side effects.
- Token creation allows admin requests through the public facade and preserves the success payload shape.
- Token listing rejects non-admin requests before DAO reads.
- Token deletion rejects non-admin requests before DAO writes.
- Focused tests, compile/import checks, private import search, diff check, and full test suite pass.
