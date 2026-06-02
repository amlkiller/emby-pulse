# Bot Admin Message Plugin Lifecycle Stop

## Goal

Continue the architecture audit lifecycle refactor by making bot-admin-message plugin event subscriptions reversible for plugins that already track subscription state.

## Requirements

- Make `Cloud115Plugin.on_disable()` unsubscribe its `bot.admin_message` handler and clear `_subscribed`.
- Make `HDHivePlugin.on_disable()` unsubscribe its `bot.admin_message` handler and clear `_subscribed`.
- Fix the existing HDHive request-search callback helper reference surfaced by lint in the touched file, preserving the existing TMDB-select flow.
- Preserve both plugins' message parsing, transfer/search behavior, config schema, routes, and one-off worker thread behavior.
- Keep existing duplicate-subscribe guards in `on_enable()`.
- Add focused regression tests that repeated enable does not duplicate subscriptions, disable removes the handler, and re-enable works in the same process.

## Acceptance Criteria

- `cloud115` repeated `on_enable()` calls register one `bot.admin_message` handler.
- `cloud115` `on_disable()` removes that handler and resets `_subscribed`.
- `hdhive` repeated `on_enable()` calls register one `bot.admin_message` handler while preserving scheduler start idempotency.
- `hdhive` `on_disable()` stops its checkin thread, removes the bot handler, clears `_subscribed`, and can re-enable later.
- HDHive request-search callbacks no longer reference an undefined helper and still dispatch through `_search_tmdb_select`.
- Focused lifecycle tests, compile, ruff, `git diff --check`, and full pytest pass in one consolidated verification pass.

## Out of Scope

- Do not change Cloud115 transfer/offline worker behavior.
- Do not change HDHive checkin/search/unlock behavior.
- Do not add event bus APIs beyond the existing `unsubscribe()` added in the previous slice.
- Do not refactor broader notification bot service subscriptions in this slice.

## Technical Notes

- Audit reference: `docs/架构审计.md` P1 issue 3, plugin lifecycle management incomplete.
- Existing event-driven lifecycle spec: `.trellis/spec/backend/directory-structure.md`.
- Current evidence:
  - `app/plugins/cloud115/plugin.py` has `_subscribed` and subscribes `bot.admin_message` in `on_enable()`, but `on_disable()` does not unsubscribe.
  - `app/plugins/hdhive/plugin.py` has `_subscribed` and subscribes `bot.admin_message` in `on_enable()`, but `on_disable()` only stops the checkin loop.
  - `ruff --select E9,F63,F7,F82` also surfaced an existing undefined `_search_hdhive_for_request` reference in `app/plugins/hdhive/plugin.py`; the file already has a neighboring callback path that builds `_tmdb_cache` and calls `_search_tmdb_select`.
