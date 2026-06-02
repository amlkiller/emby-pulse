# Notification Bot Event Subscription Stop

## Goal

Continue the architecture audit lifecycle refactor by making notification bot service EventBus subscriptions reversible on service stop.

## Requirements

- Move `SystemDaemon` `webhook.received` subscription out of construction-time side effects into a guarded lifecycle subscription.
- Move `NotificationBot` notification event subscriptions out of construction-time side effects into a guarded lifecycle subscription.
- Save stable handlers for playback start/stop events instead of subscribing anonymous lambdas that cannot be unsubscribed.
- Make `SystemDaemon.stop()` and `NotificationBot.stop()` unsubscribe their handlers and clear subscription state.
- Fix the existing `ColorTransfer` HDR fallback variable reference surfaced by lint in the touched file, preserving the intended HDR/HLG detection.
- Preserve notification event payloads, bot command behavior, webhook handling, polling behavior, and existing `EmbyPulseOrchestrator` public methods.
- Add focused regression tests for idempotent subscribe, stop unsubscribe, and restart re-subscribe behavior.

## Acceptance Criteria

- Constructing `SystemDaemon` and `NotificationBot` does not subscribe event handlers.
- Repeated `start()` calls subscribe each handler once.
- `stop()` unsubscribes every handler and clears subscription state.
- Restart after stop re-subscribes handlers in the same process.
- Playback start/stop handlers continue to call `on_playback_event(data, "start"|"stop")`.
- Media quality HDR fallback can read `ColorTransfer` without raising and maps `arib-std-b67` to HLG.
- Focused lifecycle tests, compile, ruff, `git diff --check`, and full pytest pass in one consolidated verification pass.

## Out of Scope

- Do not change notification payload shapes or mute-rule behavior.
- Do not change Telegram/WeCom polling, message sending, command parsing, or callback handling.
- Do not join or cancel notification bot polling threads in this slice.
- Do not split `bot_service.py` or introduce a public notification facade in this slice.

## Technical Notes

- Audit reference: `docs/架构审计.md` P1 issue 3, lifecycle management incomplete.
- Existing lifecycle spec: `.trellis/spec/backend/directory-structure.md`.
- Current evidence:
  - `SystemDaemon.__init__()` subscribes `webhook.received`; `SystemDaemon.stop()` only sets `running = False`.
  - `NotificationBot.__init__()` subscribes multiple notification events, including two anonymous playback lambdas; `NotificationBot.stop()` only sets `running = False`.
  - `stop_notification_services()` calls `bot.stop()`, so reversible subscriptions belong under the daemon/notifier stop lifecycle.
  - `ruff --select E9,F63,F7,F82` surfaced an existing undefined `color_transfer` reference in `get_media_quality_info(...)`; the intended source is `video_stream["ColorTransfer"]`.
