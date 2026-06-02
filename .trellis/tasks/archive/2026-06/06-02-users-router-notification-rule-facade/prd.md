# Users Router Notification Rule Public Facade Boundary

## Goal

Move the user deletion notification-rule lookup in `app/domains/users/router.py` off the private notifications admin module and through the notifications public facade, preserving existing delete-user behavior.

## Requirements

- Replace the local `app.domains.notifications.notify_admin.get_notify_rule` import in `users/router.py` with a notifications public facade call.
- Add a narrow `get_notify_rule(notify_type)` wrapper to `app/domains/notifications/public_service.py`.
- Preserve delete-user endpoint behavior, notification payload text, channel handling, web notification calls, audit logging, response payloads, and side-effect ordering.
- Add focused regression tests that prove:
  - `users/router.py` no longer imports private `notifications.notify_admin`.
  - The notifications public facade delegates `get_notify_rule` to the existing notifications implementation.
  - The delete-user notification block uses `router.notification_service.get_notify_rule` before sending bot notifications.

## Acceptance Criteria

- [ ] `users/router.py` has no direct `app.domains.notifications.notify_admin` import.
- [ ] `notifications.public_service.get_notify_rule()` delegates to the existing notifications rule implementation.
- [ ] Delete-user notification behavior still uses the same channels and response shape.
- [ ] Focused boundary tests pass.
- [ ] Compile, import, private-import scan, and full pytest suite pass before commit.

## Definition of Done

- Tests added/updated for the import boundary and public facade delegation.
- Python verification commands use `uv run`.
- Work commit is created for code/test files, followed by separate Trellis archive and journal commits.

## Technical Approach

Expose `get_notify_rule()` from `app.domains.notifications.public_service` as a thin lazy import wrapper, remove the private local import in `users/router.py`, and call the already imported `notification_service` facade inside the delete-user notification block.

## Out of Scope

- No endpoint, notification text, channel, audit, database, media API, or response behavior changes.
- No migration of other notifications private imports in this task.
- No split of `users/router.py`.

## Technical Notes

- Audit source: `docs/架构审计.md` P2 issue 6, cross-domain private import cleanup.
- Target files inspected:
  - `app/domains/users/router.py`
  - `app/domains/notifications/public_service.py`
  - `tests/test_notification_public_service_facade.py`
