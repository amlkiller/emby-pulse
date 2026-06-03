# Refactor Notification Bot Feedback Callback Service

## Goal

Continue P2 item 5 from `docs/架构审计.md` by splitting the resource-feedback callback branch out of the large `NotificationBot._handle_callback` method in `app/domains/notifications/bot_service.py`. This slice extracts `feed_*` callback handling into a notifications-local service while preserving message edit behavior and DAO updates.

## Requirements

- Move `feed_*` callback handling out of `_handle_callback` into a new domain-local service module.
- Preserve action/status mapping for `feed_fix_*`, `feed_done_*`, and `feed_reject_*`.
- Preserve feedback DAO status updates.
- Preserve caption vs text edit behavior, operator suffix, reply markup clearing, Telegram method names, proxy usage, timeout, and swallowed Telegram edit failures.
- Keep `_handle_callback` as the legacy entrypoint and preserve callback order.
- Add focused boundary tests for the extracted feedback callback behavior.

## Acceptance Criteria

- [ ] `bot_service.py` delegates `feed_*` callback handling to a new service.
- [ ] New tests cover fix/done/reject mapping, caption edit, text edit, unknown action no-op, and swallowed Telegram edit failure.
- [ ] Focused tests pass.
- [ ] Import check passes for `bot_service.py` and the new service module.
- [ ] Full test suite passes.
- [ ] Code/test changes are committed separately from task archive and journal commits.

## Definition of Done

- Behavior-preserving refactor only; no feedback status, text, or payload changes.
- No extraction of request approval, risk-ban, or message-center callbacks in this slice.
- Trellis task is archived after the code/test commit.
- Session journal records the work commit.

## Out of Scope

- Changing feedback DAO contracts.
- Changing Telegram callback answering or admin permission logic.
- Refactoring `req_*` request approval workflows.

## Technical Notes

- Target file: `app/domains/notifications/bot_service.py`.
- New module should follow existing extracted notification bot service/provider style.
- Preserve legacy monkeypatch compatibility by configuring dependencies from `bot_service.py`.
