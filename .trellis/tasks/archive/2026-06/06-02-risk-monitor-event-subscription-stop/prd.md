# Risk Monitor Event Subscription Stop

## Goal

Continue the architecture audit lifecycle refactor by making the bootstrap-started risk monitor remove its event-bus subscriptions when stopped.

## Requirements

- Track whether `start_risk_monitor()` has subscribed risk monitor handlers.
- Keep repeated `start_risk_monitor()` idempotent and avoid duplicate event-bus handlers.
- Make `stop_risk_monitor()` unsubscribe `notify.playback.start` and `notify.risk.alert` handlers and clear subscription state.
- Preserve existing risk scan behavior, thread stop behavior, stop-event semantics, and bootstrap registry wiring.
- Add focused regression coverage for start/stop/restart event subscription lifecycle.

## Acceptance Criteria

- Repeated `start_risk_monitor()` calls register one `notify.playback.start` handler and one `notify.risk.alert` handler.
- `stop_risk_monitor()` removes both handlers from the event bus and resets risk monitor state.
- Restart after stop re-subscribes both handlers in the same process.
- Existing risk monitor thread lifecycle tests continue to pass.
- Focused lifecycle tests, compile, ruff, `git diff --check`, and full pytest pass in one consolidated verification pass.

## Out of Scope

- Do not change risk scan policy, notification payload shape, user ban/warn behavior, or media-server calls.
- Do not change notification bot service event subscriptions in this slice.
- Do not modify bootstrap registry ordering.

## Technical Notes

- Audit reference: `docs/架构审计.md` P1 issue 3, lifecycle management incomplete.
- Existing lifecycle spec: `.trellis/spec/backend/directory-structure.md`.
- Current evidence: `app/domains/risk/risk_service.py` subscribes `notify.playback.start` and `notify.risk.alert` in `start_risk_monitor()`, while `stop_risk_monitor()` only stops the thread and does not unsubscribe those handlers.
