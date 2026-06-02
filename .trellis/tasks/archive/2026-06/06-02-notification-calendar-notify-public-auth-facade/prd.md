# Notification Calendar Notify Public Auth Facade Boundary

## Goal

Move `app/domains/notifications/calendar_notify.py` admin checks off the private users auth module and through the users public facade, preserving existing calendar notification API behavior and lifecycle behavior.

## Requirements

- Replace the private `app.domains.users.auth` import in `app/domains/notifications/calendar_notify.py` with the users public facade.
- Route all existing API admin checks in the module through `app.domains.users.public_service`.
- Preserve endpoint paths, response payloads/messages, config persistence behavior, manual/test send behavior, and service lifecycle code.
- Add focused regression tests that prove:
  - `calendar_notify.py` no longer imports private users auth.
  - Representative non-admin routes deny before DAO/send side effects.
  - Representative admin routes call through the public facade and preserve success responses.

## Verification

- Run focused pytest for the new boundary test.
- Compile the changed calendar notify module and test file.
- Import `app.domains.notifications.calendar_notify` through the project `uv` environment.
- Search the changed module for private users auth imports.
- Run `git diff --check` for changed files.
- Run the full test suite before committing.
