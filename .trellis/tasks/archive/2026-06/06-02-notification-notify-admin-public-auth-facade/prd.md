# Notification Notify Admin Public Auth Facade Boundary

## Goal

Move `app/domains/notifications/notify_admin.py` admin checks off the private users auth module and through the users public facade, preserving existing notification admin route behavior.

## Requirements

- Replace the private `app.domains.users.auth` import in `app/domains/notifications/notify_admin.py` with the users public facade.
- Route all existing `is_admin_user(...)` API checks in the module through `app.domains.users.public_service`.
- Preserve endpoint paths, response payloads/messages, page rendering behavior, rule defaults, DAO calls, and notification-channel config behavior.
- Add focused regression tests that prove:
  - `notify_admin.py` no longer imports private users auth.
  - Representative non-admin routes deny before DAO/config side effects.
  - Representative admin routes call through the public facade and preserve success responses.

## Verification

- Run focused pytest for the new boundary test.
- Compile the changed notify admin module and test file.
- Import `app.domains.notifications.notify_admin` through the project `uv` environment.
- Search the changed module for private users auth imports.
- Run `git diff --check` for changed files.
- Run the full test suite before committing.
