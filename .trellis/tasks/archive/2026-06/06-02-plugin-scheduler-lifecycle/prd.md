# Plugin Scheduler Lifecycle Stop Hooks

## Goal

Close the remaining P1 lifecycle gap from `docs/架构审计.md` for built-in plugin schedulers. Enabled plugins that own background scheduler/check loops must stop cleanly during app shutdown and be safe to re-enable in the same process.

## Requirements

* Add a plugin runtime shutdown boundary that disables enabled plugin instances during bootstrap shutdown.
* Register that shutdown boundary in the bootstrap service registry without changing plugin route discovery or normal enable/disable API behavior.
* Keep plugin lifecycle behavior idempotent: duplicate enable should not create duplicate scheduler threads, and disable should interrupt scheduler waits, join briefly, and clear stopped handles.
* Bring scheduler-style built-in plugins that still use old state flags into the current stop-event lifecycle shape.
* Preserve existing plugin IDs, routes, config keys, response shapes, and scheduler timing semantics.
* Add focused regression coverage for plugin scheduler stop/restart behavior and bootstrap shutdown integration.

## Acceptance Criteria

* [ ] Bootstrap shutdown invokes plugin disable hooks for enabled plugins.
* [ ] Repeated bootstrap stop calls are harmless when no registry or no plugins are active.
* [ ] `emby_restart` scheduler can enable, disable, and re-enable without leaving duplicate live threads.
* [ ] `view_report` scheduler can enable, disable, and re-enable without leaving duplicate live threads.
* [ ] Verification uses `uv run --with-requirements requirements.txt` commands.
* [ ] `docs/架构审计.md` records the completed plugin scheduler lifecycle progress.

## Definition of Done

* Focused tests pass.
* Changed Python files compile.
* Full test suite passes unless an unrelated pre-existing failure is identified.
* Work is committed as one coherent refactor commit.

## Technical Approach

Add a narrow `disable_enabled_plugins()` helper to `app.plugins` that iterates currently enabled registry entries and calls each plugin's existing `disable()` hook. Register it as a stop-only bootstrap service so `stop_bootstrap_services()` participates in plugin cleanup without changing startup ordering.

For scheduler plugins, keep the existing thread attributes for compatibility but make the stop event the authoritative loop signal. `on_enable()` clears the event and starts only when the previous thread is not alive; `on_disable()` sets the event, joins briefly, and clears the handle once stopped.

## Out of Scope

* Rewriting plugin background one-shot worker threads spawned by request handlers.
* Moving plugin internals behind new facades.
* Changing scheduler cron semantics or plugin UI behavior.
* Refactoring all large plugin files.

## Technical Notes

* Audit source: `docs/架构审计.md`, P1 item 3 says plugin scheduler lifecycle still needs completion.
* Spec source: `.trellis/spec/backend/directory-structure.md` defines the desired plugin lifecycle contract.
* Plugin discovery currently lives in `app/plugins/__init__.py`; route registration calls `discover_plugins()` from `app/bootstrap/plugin_routes.py`.
* Bootstrap services are orchestrated by `app/bootstrap/services.py` and `app/bootstrap/service_registry.py`.
* Existing scheduler plugins mostly already use stop events; `emby_restart` and `view_report` still keep a separate `scheduler_running` loop flag.
