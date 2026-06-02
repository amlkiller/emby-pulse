# System Router Public Auth Facade Boundary

## Goal

Move `app/domains/system/router.py` admin checks off the private users auth module and through the users public facade, preserving existing route behavior and response shapes.

## Requirements

- Replace the private `app.domains.users.auth` import in `app/domains/system/router.py` with the users public facade.
- Route all existing `is_admin_user(request)` checks in the module through the public facade.
- Preserve all endpoint paths, status/message payloads, settings behavior, diagnostic behavior, and side-effect ordering.
- Add focused regression tests that prove:
  - `system/router.py` no longer imports private users auth.
  - Representative non-admin routes deny access before reading or writing protected data.
  - A representative admin route calls through the facade and preserves its success response.

## Verification

- Run focused pytest for the new boundary test.
- Compile the changed router and test file.
- Import `app.domains.system.router` through the project `uv` environment.
- Search the changed router for private users auth imports.
- Run `git diff --check` for changed files.
- Run the full test suite before committing.
