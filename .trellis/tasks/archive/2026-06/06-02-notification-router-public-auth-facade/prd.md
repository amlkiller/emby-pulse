# Notification Router Public Auth Facade Boundary

## Goal

Move `app/domains/notifications/router.py` admin checks off the private users auth module and through the users public facade, preserving existing notification center API behavior.

## Requirements

- Replace the private `app.domains.users.auth` import in `app/domains/notifications/router.py` with the users public facade.
- Route all existing route-level admin checks in the module through `app.domains.users.public_service`.
- Preserve endpoint paths, response payloads/messages, table bootstrap behavior, DAO calls, and notification side effects.
- Add focused regression tests that prove:
  - `router.py` no longer imports private users auth.
  - Representative non-admin routes deny before DAO side effects.
  - Representative admin routes call through the public facade and preserve success responses.

## Acceptance Criteria

- [ ] Changed router module has no private `app.domains.users.auth` import.
- [ ] Existing unauthorized responses still return `{"success": False, "msg": "需要管理员权限"}`.
- [ ] Admin success paths still call the existing DAO helpers in the same order.
- [ ] Focused boundary tests pass.
- [ ] Compile, import, diff hygiene, private-import scan, and full pytest suite pass before commit.

## Definition of Done

- Tests added for the import boundary and representative authorization behavior.
- Python verification commands use `uv run --with-requirements requirements.txt`.
- Work commit is created for code/test files, followed by separate Trellis archive and journal commits.

## Technical Approach

Use the same pattern as the adjacent notification facade-boundary refactors: import `app.domains.users.public_service` as `user_service`, replace `is_admin_user(request)` guards with `user_service.is_admin_user(request)`, and keep response shapes and side-effect ordering unchanged.

## Out of Scope

- No endpoint, schema, response, or DAO behavior changes.
- No migration of users-domain-internal imports.
- No changes to notification bot, messages, playback stats, or media request routers in this task.

## Technical Notes

- Target file inspected: `app/domains/notifications/router.py`.
- Existing completed slices provide the local test style:
  - `tests/test_notification_notify_rules_public_auth_facade_boundary.py`
  - `tests/test_notification_notify_admin_public_auth_facade_boundary.py`
  - `tests/test_notification_calendar_notify_public_auth_facade_boundary.py`
