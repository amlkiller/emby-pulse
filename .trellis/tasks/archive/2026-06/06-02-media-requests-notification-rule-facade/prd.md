# Media Requests Notification Rule Public Facade Boundary

## Goal

Move notification-rule lookups in `app/domains/media_requests/router.py` off the private notifications admin module and through the notifications public facade, preserving all existing request, feedback, and registration notification behavior.

## Requirements

- Replace local `app.domains.notifications.notify_admin.get_notify_rule` imports in `media_requests/router.py` with calls to the already imported `notification_service.get_notify_rule`.
- Preserve existing notification type keys: `request_new`, `request_status`, `feedback_new`, and `user_register`.
- Preserve channel selection, fallback behavior, message text, response payloads, and side-effect ordering.
- Keep this task scoped to `media_requests/router.py` and focused regression tests.

## Acceptance Criteria

- [ ] `media_requests/router.py` has no direct `app.domains.notifications.notify_admin` import.
- [ ] Submit-request notification behavior uses `router.notification_service.get_notify_rule("request_new")` before sending photo or web notifications.
- [ ] Batch request status notification behavior uses `router.notification_service.get_notify_rule("request_status")` before querying status notification rows.
- [ ] Feedback notification behavior uses `router.notification_service.get_notify_rule("feedback_new")` before sending photo or web notifications.
- [ ] User community registration notification behavior uses `router.notification_service.get_notify_rule("user_register")` and preserves its existing fallback when the rule is disabled.
- [ ] Focused boundary tests pass.
- [ ] Compile, import, private-import scan, and full pytest suite pass before commit.

## Definition of Done

- Tests added/updated for the media requests router import boundary and representative public facade call paths.
- Python verification commands use `uv run`.
- Work commit is created for code/test files, followed by separate Trellis archive and journal commits.

## Technical Approach

Use the existing `from app.domains.notifications import public_service as notification_service` import at the top of `media_requests/router.py`. Remove local private imports of `get_notify_rule` and call `notification_service.get_notify_rule(...)` in place. Add focused AST and monkeypatch tests following the existing users-router notification facade boundary test pattern.

## Out of Scope

- No endpoint, notification text, channel, audit, database, media API, or response behavior changes.
- No migration of private notification imports inside the notifications domain itself.
- No broader split of `media_requests/router.py`.

## Technical Notes

- Audit source: `docs/架构审计.md` P2 issue 6, cross-domain private import cleanup.
- Public facade exists from the previous slice: `app.domains.notifications.public_service.get_notify_rule()`.
- Target files inspected:
  - `app/domains/media_requests/router.py`
  - `tests/test_users_router_notification_rule_facade_boundary.py`
  - `tests/test_notification_public_service_facade.py`
