# Risk Service User Bot Notification Public Facade Boundary

## Goal

Move user-bot notification sends in `app/domains/risk/risk_service.py` off the private notifications user bot module and through the notifications public facade, preserving existing risk warning and auto-ban notification behavior.

## Requirements

- Replace local `app.domains.notifications.user_bot_service._send` imports in `risk_service.py` with calls through `notifications.public_service.send_user_bot_message`.
- Preserve TG binding lookup, message text, logging, and exception handling behavior.
- Keep this task scoped to the risk service notification boundary and focused regression tests.

## Acceptance Criteria

- [ ] `risk_service.py` has no direct `app.domains.notifications.user_bot_service` import.
- [ ] `_send_user_warning()` looks up the bound TG user and calls `notification_service.send_user_bot_message(tg_user_id, message)`.
- [ ] `_send_user_ban_notify()` looks up the bound TG user and calls `notification_service.send_user_bot_message(tg_user_id, message)`.
- [ ] No notification is sent when a user has no TG binding.
- [ ] Focused boundary tests pass.
- [ ] Compile, import, private-import scan, and full pytest suite pass before commit.

## Definition of Done

- Tests added for the import boundary and the two risk user-bot notification paths.
- Python verification commands use `uv run`.
- Work commit is created for code/test files, followed by separate Trellis archive and journal commits.

## Technical Approach

Import `app.domains.notifications.public_service` as `notification_service` in `risk_service.py`, remove private local `_send` imports, and replace `_send(tg_user_id, msg)` with `notification_service.send_user_bot_message(tg_user_id, msg)`.

## Out of Scope

- No changes to risk scan scheduling, policy decisions, media server calls, system notification behavior, event publication, or message content.
- No migration of other private notification imports outside `risk_service.py`.
- No split of `risk_service.py`.

## Technical Notes

- Audit source: `docs/架构审计.md` P2 issue 6, cross-domain private import cleanup.
- Public facade exists: `app.domains.notifications.public_service.send_user_bot_message(chat_id, text, reply_markup=None)`.
- Target files inspected:
  - `app/domains/risk/risk_service.py`
  - `app/domains/notifications/public_service.py`
  - `tests/test_risk_router_public_auth_facade_boundary.py`
