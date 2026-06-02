# Notification Bot Polling Lifecycle Convergence

## Context

`docs/架构审计.md` lists incomplete lifecycle management as a P1 architecture risk. `app/domains/notifications/bot_service.py` is a bootstrap-started notification service. `SystemDaemon` now has stoppable scheduler/library threads, but `NotificationBot` still starts a Telegram polling thread without a stop event, join, or handle cleanup.

## Scope

- Add a stop event to `NotificationBot`.
- Make `NotificationBot.start()` clear the stop event before starting polling.
- Name the polling thread for lifecycle tests and diagnostics.
- Make `NotificationBot.stop()` set the stop event, unsubscribe events, join the polling thread briefly, and clear stopped thread handles.
- Replace fixed retry sleeps in `_polling_loop()` with stop-event waits.
- Preserve Telegram polling behavior, event subscriptions, command setup, and message/callback handling.
- Add focused regression tests for polling thread stop/restart behavior.

## Out Of Scope

- Wrapper/pass-through function cleanup handled on other branches.
- User bot service polling/scheduler lifecycle cleanup.
- Notification message formatting or route response changes.

## Verification

- Compile changed files with `uv run python -m compileall`.
- Run focused notification lifecycle tests.
- Run full `uv run pytest tests/ -v` before committing.
