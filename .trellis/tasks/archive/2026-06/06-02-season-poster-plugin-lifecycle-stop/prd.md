# Season Poster Plugin Lifecycle Stop

## Goal

Continue the architecture audit lifecycle refactor by making the season poster updater plugin's webhook subscription lifecycle explicit, idempotent, and reversible.

## Requirements

- Add an unsubscribe capability to the shared event bus so event-driven plugins can remove handlers during disable.
- Make `SeasonPosterUpdaterPlugin.on_enable()` subscribe to `webhook.received` at most once per plugin instance.
- Make `SeasonPosterUpdaterPlugin.on_disable()` unsubscribe from `webhook.received` and clear plugin subscription state.
- Preserve the plugin's webhook payload handling, route behavior, cache behavior, and media-server update logic.
- Keep one-off webhook processing asynchronous, but prevent disabled plugins from continuing to receive new webhook events.
- Add focused regression tests for event bus unsubscribe behavior and season poster enable/disable subscription idempotency.

## Acceptance Criteria

- Repeated `on_enable()` calls do not register duplicate webhook handlers.
- `on_disable()` removes the plugin handler from the event bus.
- Re-enable after disable registers the handler again in the same process.
- Publishing or handling new webhook events after disable is prevented by the removed subscription.
- Focused tests, compile, ruff, `git diff --check`, and full pytest pass in one consolidated verification pass.

## Out of Scope

- Do not change season poster API routes, config schema, cache schema, or media-server request behavior.
- Do not attempt to cancel an already-running poster update worker thread in this slice.
- Do not refactor `season_poster_updater/plugin.py` beyond the lifecycle subscription boundary.
- Do not change `cloud115` one-off transfer/offline worker behavior in this slice.

## Technical Notes

- Audit reference: `docs/架构审计.md` P1 issue 3, plugin scheduler/lifecycle management incomplete.
- Existing lifecycle spec: `.trellis/spec/backend/directory-structure.md`.
- Current evidence: `app/plugins/season_poster_updater/plugin.py` subscribes to `webhook.received` in `on_enable()` but `on_disable()` does not unsubscribe.
- `app/core/event_bus.py` currently exposes `subscribe()` and `publish()` only.
