# System Pro Public Auth Facade Boundary

## Goal

Move `app/domains/system/pro.py` off direct private `app.domains.users.auth` imports and route its admin authorization checks through the users public facade, while preserving the existing Pro activation/status API behavior.

## Scope

- Update `app/domains/system/pro.py` to import the users public service facade for admin checks.
- Preserve route URLs, response shapes, messages, license behavior, and notification behavior.
- Add a focused import-boundary/behavior test proving the module does not import private users auth and that admin gating still controls activation and status paths.
- Update existing Pro status tests to patch the new facade dependency location.

## Acceptance Criteria

- `app/domains/system/pro.py` has no `from app.domains.users.auth ...` or `import app.domains.users.auth` import.
- Non-admin activation returns the existing error response and does not replace license state.
- Admin activation strips the license key, uses the machine id, replaces license state, and returns the existing success response.
- Non-admin status returns the existing permission error response.
- Existing Pro status payload tests still pass.
- Focused tests, compile/import checks, private import search, diff check, and full test suite pass.
