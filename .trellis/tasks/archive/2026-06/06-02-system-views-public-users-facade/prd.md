# System Views Public Users Facade Boundary

## Goal

Move `app/domains/system/views.py` permission behavior off private users auth imports and through the users public facade, preserving existing page routing and permission response behavior.

## Requirements

- Remove direct imports from `app.domains.users.auth` in `app/domains/system/views.py`.
- Expose the page-permission map through `app.domains.users.public_service` without copying permission data into the system domain.
- Route `check_page_permission()` permission checks through the users public facade.
- Preserve existing login redirects, legacy-session compatibility, first-allowed-page routing, forbidden HTML response shape, and template context behavior.
- Add focused regression tests proving:
  - `system/views.py` does not import private users auth.
  - `users.public_service` delegates the page-permission map to users auth.
  - `check_page_permission()` uses the public facade for sub-account permission checks.
  - `get_first_allowed_page()` uses the public facade permission map while preserving admin and sub-account behavior.

## Verification

- Run focused pytest for the updated/new boundary tests.
- Compile changed files.
- Import `app.domains.system.views` through the project `uv` environment.
- Search the changed system views module for private users auth imports.
- Run `git diff --check` for changed files.
- Run the full test suite before committing.
