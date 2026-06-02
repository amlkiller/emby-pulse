# Notification Messages Public Auth Facade Boundary

## Goal

Move `app/domains/notifications/messages.py` admin checks off the private users auth module and through the users public facade, preserving existing message center API behavior.

## Requirements

- Replace the private `app.domains.users.auth` import in `app/domains/notifications/messages.py` with the users public facade.
- Route all existing `is_admin_user(request)` checks in the module through `app.domains.users.public_service`.
- Preserve endpoint paths, response payloads/messages, DAO calls, media API calls, notification behavior, message sanitization, and side-effect ordering.
- Add focused regression tests that prove:
  - `messages.py` no longer imports private users auth.
  - Representative non-admin routes deny before DAO/media/config side effects.
  - Representative admin routes call through the public facade and preserve success responses.

## Acceptance Criteria

- [ ] Changed messages module has no private `app.domains.users.auth` import.
- [ ] Existing unauthorized responses still return the same payloads.
- [ ] Admin success paths still call existing helpers in the same order.
- [ ] Focused boundary tests pass.
- [ ] Compile, import, diff hygiene, private-import scan, and full pytest suite pass before commit.

## Definition of Done

- Tests added for the import boundary and representative authorization behavior.
- Python verification commands use `uv run --with-requirements requirements.txt`.
- Work commit is created for code/test files, followed by separate Trellis archive and journal commits.

## Technical Approach

Import `app.domains.users.public_service` as `user_service`, replace each existing `is_admin_user(request)` route guard with `user_service.is_admin_user(request)`, and avoid restructuring message center logic.

## Out of Scope

- No endpoint, schema, response, DAO, notification, or bot behavior changes.
- No migration of users-domain-internal imports.
- No changes to playback stats or bootstrap modules in this task.

## Technical Notes

- Target file inspected: `app/domains/notifications/messages.py`.
- Existing completed slices provide the local test style:
  - `tests/test_notification_bot_public_auth_facade_boundary.py`
  - `tests/test_notification_router_public_auth_facade_boundary.py`
