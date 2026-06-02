# Notification Public Service Facade

## Goal

Continue the architecture audit P2 cross-domain boundary work by introducing a narrow public notification service facade and moving non-notification domains/plugins away from direct imports of `app.domains.notifications.bot_service.bot`.

## Requirements

- Add a public notifications facade module that exposes the current bot operations needed by external domains/plugins.
- Preserve existing bot behavior by delegating to the existing `EmbyPulseOrchestrator` singleton.
- Migrate domain/plugin callers outside `app/domains/notifications/` from direct `bot_service.bot` imports to the facade.
- Preserve message text, photos, reply markup, platform selection, channel behavior, report push behavior, and return values.
- Keep notification-domain-internal uses of `bot_service.bot` out of scope for this slice unless required for tests.
- Add focused regression tests that prove the facade delegates correctly and external callers no longer import `bot_service.bot` directly.
- Do one consolidated verification pass and one work commit for this task.

## Acceptance Criteria

- A module such as `app/domains/notifications/public_service.py` exists and exposes narrow functions for:
  - `send_message(...)`
  - `send_photo(...)`
  - `edit_message(...)`
  - `send_to_channels(...)`
  - `push_report_now(...)`
- External modules under `app/domains/*` and `app/plugins/*`, excluding `app/domains/notifications/*`, no longer import `app.domains.notifications.bot_service.bot`.
- Call-site arguments and behavior are unchanged for migrated callers.
- Facade delegation tests cover representative return-value and argument forwarding.
- Boundary tests fail if external domains/plugins reintroduce direct `bot_service.bot` imports.
- Compile, focused tests, ruff `E9,F63,F7,F82`, `git diff --check`, and full pytest pass in one consolidated verification pass.

## Out of Scope

- Do not split `bot_service.py`.
- Do not change `EmbyPulseOrchestrator`, `NotificationBot`, Telegram, WeCom, or channel sending behavior.
- Do not migrate notification-domain-internal direct `bot` usage in this slice.
- Do not introduce async queues, retries, new notification payloads, or typed notification DTOs.
- Do not migrate user-bot private helpers such as `_send` in this slice.

## Technical Approach

- Create `app/domains/notifications/public_service.py` with thin wrapper functions that import/use `bot_service.bot` internally.
- Replace external imports of `bot` with facade function imports in:
  - media request, users, points, reports, system modules
  - plugin modules that currently call `bot.send_message`, `bot.send_photo`, `bot.edit_message`, `bot.send_to_channels`
- Add a focused AST boundary test for external direct imports.
- Add unit tests that monkeypatch the facade's bot provider and assert arguments/return values are forwarded.

## Technical Notes

- Audit reference: `docs/架构审计.md` P2 issue 6, cross-domain direct imports.
- Existing architecture spec: `.trellis/spec/backend/directory-structure.md` says cross-domain behavior should prefer a public service function, narrow facade, or event boundary.
- Current direct external imports include `media_requests/router.py`, `points/router.py`, `reports/router.py`, `system/tasks.py`, `system/views.py`, `users/router.py`, and multiple plugins.
