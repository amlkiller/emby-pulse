# Media Requests User Bot Notification Public Facade Boundary

## Goal

Move request-status user bot notification sends in `app/domains/media_requests/router.py` off the private notifications user bot module and through the notifications public facade, preserving existing status notification behavior.

## Requirements

- Add a narrow public facade wrapper in `app/domains/notifications/public_service.py` for sending a user-bot photo message.
- Replace the local `app.domains.notifications.user_bot_service._send` / `_tg_api` import in `media_requests/router.py` with calls through the notifications public facade.
- Preserve existing notification rule lookup, TG binding lookup, message text, photo payload fields, text fallback, logging, and exception behavior.
- Keep this task scoped to the media requests request-status notification send boundary and focused regression tests.

## Acceptance Criteria

- [x] `media_requests/router.py` has no direct `app.domains.notifications.user_bot_service` import.
- [x] `notifications.public_service.send_user_bot_photo()` delegates to the existing user bot `_tg_api("sendPhoto", ...)` implementation.
- [x] Request status notifications use `router.notification_service.send_user_bot_photo(...)` when a poster image URL exists.
- [x] Request status notifications use `router.notification_service.send_user_bot_message(...)` when no poster image URL exists.
- [x] Users without TG bindings are still skipped without sending.
- [x] Focused boundary tests pass.
- [x] Compile, import, private-import scan, and full pytest suite pass before commit.

## Definition of Done

- Tests added/updated for public facade delegation and media requests request-status notification send boundary.
- Python verification commands use `uv run`.
- Work commit is created for code/test files, followed by separate Trellis archive and journal commits.

## Technical Approach

Add `send_user_bot_photo(chat_id, photo, caption, parse_mode="HTML")` to `app.domains.notifications.public_service` as a thin wrapper around the existing user bot `_tg_api("sendPhoto", ...)` payload shape. In `media_requests/router.py`, replace `_tg_api("sendPhoto", {...})` with the new facade call and `_send(...)` with `notification_service.send_user_bot_message(...)`.

## Out of Scope

- No changes to notification rules, request status state transitions, TG binding queries, notification text, route URLs, response shapes, or media request DAO behavior.
- No migration of other private notification imports outside this `media_requests/router.py` status notification path.
- No split of `media_requests/router.py` or notifications user bot internals.

## Technical Notes

- Audit source: `docs/架构审计.md` P2 issue 6, cross-domain private import cleanup.
- Existing text facade: `app.domains.notifications.public_service.send_user_bot_message(chat_id, text, reply_markup=None)`.
- Target files inspected:
  - `app/domains/media_requests/router.py`
  - `app/domains/notifications/public_service.py`
  - `tests/test_notification_public_service_facade.py`
  - `tests/test_media_requests_router_notification_rule_facade_boundary.py`
