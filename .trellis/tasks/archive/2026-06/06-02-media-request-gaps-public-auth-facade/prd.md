# Media Request Gaps Public Auth Facade Boundary

## Goal

Move `app/domains/media_requests/gaps.py` admin checks off the private users auth module and through the users public facade, preserving existing gap-management route behavior.

## Requirements

- Replace the private `app.domains.users.auth` import in `app/domains/media_requests/gaps.py` with the users public facade.
- Route all existing `is_admin_user(...)` checks in the module through the public facade.
- Preserve all endpoint paths, response payloads, optional internal-call behavior where `request is None`, scan state behavior, and side-effect ordering.
- Add focused regression tests that prove:
  - `gaps.py` no longer imports private users auth.
  - Representative non-admin routes deny before scan/config/download side effects.
  - A representative admin route calls through the public facade and preserves its success response.
  - Internal helper-style calls that pass `request=None` still skip admin checks.

## Verification

- Run focused pytest for the new boundary test.
- Compile the changed gaps module and test file.
- Import `app.domains.media_requests.gaps` through the project `uv` environment.
- Search the changed gaps module for private users auth imports.
- Run `git diff --check` for changed files.
- Run the full test suite before committing.
