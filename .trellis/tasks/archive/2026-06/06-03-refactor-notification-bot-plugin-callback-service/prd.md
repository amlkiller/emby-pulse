# Refactor Notification Bot Plugin Callback Service

## Goal

Continue P2 item 5 from `docs/架构审计.md` by splitting a narrow part of the large `NotificationBot._handle_callback` method out of `app/domains/notifications/bot_service.py`. This slice extracts plugin callback pre-dispatch for Cloud115 and HDHive callbacks into a notifications-local service while preserving callback order and swallowed-error behavior.

## Requirements

- Move plugin callback branches for `p115_*`, `hdhive_sr_*`, `hdhive_tmdb_*`, `hdhive_tmdbprev_*`, `hdhive_tmdbnext_*`, `hdhive_tmdbpage_*`, `hdhive_page_*`, and `req_hdhive_*` out of `_handle_callback`.
- Preserve callback order relative to existing behavior after the Telegram callback answer and before built-in callback handlers.
- Preserve dynamic plugin imports so optional plugins remain lazy and missing plugin failures are swallowed/logged as before.
- Preserve HDHive TMDB pagination logging messages.
- Keep `_handle_callback` as the legacy entrypoint.
- Add focused boundary tests for plugin callback dispatch behavior.

## Acceptance Criteria

- [ ] `bot_service.py` delegates the plugin callback pre-dispatch to a new service.
- [ ] New tests cover Cloud115 transfer/offline callbacks, HDHive search/TMDB/page callbacks, pagination logging, request-HDHive error logging, and false/no-match behavior.
- [ ] Focused tests pass.
- [ ] Import check passes for `bot_service.py` and the new service module.
- [ ] Full test suite passes.
- [ ] Code/test changes are committed separately from task archive and journal commits.

## Definition of Done

- Behavior-preserving refactor only; no callback data format changes.
- No extraction of request approval, feedback, risk-ban, or message-center callback branches in this slice.
- Trellis task is archived after the code/test commit.
- Session journal records the work commit.

## Out of Scope

- Refactoring `req_approve`, `req_manual`, `req_reject`, or `feed_*` workflows.
- Changing plugin callback APIs.
- Changing Telegram answerCallbackQuery behavior.

## Technical Notes

- Target file: `app/domains/notifications/bot_service.py`.
- New module should follow existing extracted notification bot service/provider style.
- Optional plugin imports should remain inside handler functions to avoid import-time side effects.
