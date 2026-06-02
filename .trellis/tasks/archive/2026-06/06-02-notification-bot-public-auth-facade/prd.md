# Notification Bot Public Auth Facade Boundary

## Goal

Move `app/domains/notifications/bot.py` admin checks off the private users auth module and through the users public facade, preserving existing bot administration API behavior.

## Requirements

- Replace the private `app.domains.users.auth` import in `app/domains/notifications/bot.py` with the users public facade.
- Route all existing route-level `is_admin_user(request)` checks in the module through `app.domains.users.public_service`.
- Preserve endpoint paths, response payloads/messages, webhook behavior, bot setting persistence, audit logging, registration/lottery behavior, and side-effect ordering.
- Add focused regression tests that prove:
  - `bot.py` no longer imports private users auth.
  - Representative non-admin routes deny before config/DAO/request-body side effects.
  - Representative admin routes call through the public facade and preserve success responses.

## Acceptance Criteria

- [ ] Changed bot module has no private `app.domains.users.auth` import.
- [ ] Existing unauthorized responses still return the same payloads.
- [ ] Admin success paths still call existing helpers in the same order.
- [ ] Focused boundary tests pass.
- [ ] Compile, import, diff hygiene, private-import scan, and full pytest suite pass before commit.

## Definition of Done

- Tests added for the import boundary and representative authorization behavior.
- Python verification commands use `uv run --with-requirements requirements.txt`.
- Work commit is created for code/test files, followed by separate Trellis archive and journal commits.

## Technical Approach

Import `app.domains.users.public_service` as `user_service`, replace each existing `is_admin_user(request)` route guard with `user_service.is_admin_user(request)`, and avoid restructuring webhook or bot administration logic.

## Out of Scope

- No endpoint, schema, response, DAO, webhook, bot lifecycle, or notification behavior changes.
- No migration of users-domain-internal imports.
- No changes to notification messages or playback stats in this task.

## Technical Notes

- Target file inspected: `app/domains/notifications/bot.py`.
- Existing completed slices provide the local test style:
  - `tests/test_notification_router_public_auth_facade_boundary.py`
  - `tests/test_media_requests_router_public_auth_facade_boundary.py`
