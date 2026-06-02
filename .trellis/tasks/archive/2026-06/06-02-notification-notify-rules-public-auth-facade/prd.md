# Notification Notify Rules Public Auth Facade Boundary

## Goal

Move `app/domains/notifications/notify_rules.py` admin checks off the private users auth module and through the users public facade, preserving existing notification mute-rule API behavior.

## Requirements

- Replace the private `app.domains.users.auth` import in `app/domains/notifications/notify_rules.py` with the users public facade.
- Route all existing admin checks in the module through `app.domains.users.public_service`.
- Preserve endpoint paths, async signatures, response payloads, login/admin error messages, DAO calls, and media server user-list behavior.
- Add focused regression tests that prove:
  - `notify_rules.py` no longer imports private users auth.
  - Representative non-admin routes deny before DAO/media side effects.
  - Representative admin routes call through the public facade and preserve success responses.

## Verification

- Run focused pytest for the new boundary test.
- Compile the changed notify rules module and test file.
- Import `app.domains.notifications.notify_rules` through the project `uv` environment.
- Search the changed module for private users auth imports.
- Run `git diff --check` for changed files.
- Run the full test suite before committing.
