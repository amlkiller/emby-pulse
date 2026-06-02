# Remove Notification Orchestrator Pass-Through Methods

## Goal

Reduce notification-domain indirection by removing methods on
`EmbyPulseOrchestrator` that only forward arguments to `NotificationBot` or
`SystemDaemon` without adding validation, orchestration, error handling, or
boundary semantics.

## Scope

- Update notification-domain callers to invoke the owning runtime object
  directly, such as `bot.notifier` for notification delivery and `bot.daemon`
  for daemon-owned queue work.
- Keep `EmbyPulseOrchestrator.start()` and `stop()` because they orchestrate
  multiple runtime components.
- Keep functions that provide a public cross-domain boundary, including
  `app.domains.notifications.public_service`; only simplify its internal path
  if behavior remains unchanged.
- Keep behavior, route responses, message payloads, and startup/shutdown side
  effects stable.

## Non-Goals

- Do not remove public notification facade functions used by plugins and other
  domains.
- Do not rename `NotificationBot` or `SystemDaemon`.
- Do not change Telegram, WeCom, or channel notification behavior.

## Acceptance Criteria

- No remaining pure `EmbyPulseOrchestrator` method that only forwards to
  `self.notifier` or `self.daemon`.
- Existing notification facade tests still pass, with tests updated only to
  reflect the shorter internal call path.
- Changed Python files compile through `uv run`.
- Relevant notification tests pass, and run the full test suite unless blocked.
