# Remove Plugin Log Alias Wrappers

## Goal

Remove private plugin `_log()` compatibility aliases that only forward to
`PluginBase.log()` with the same `message` and `level` arguments.

## Scope

- Replace internal `self._log(...)` calls with `self.log(...)` in plugins where
  `_log()` is a pure pass-through.
- Remove the pure `_log()` method definitions from:
  - `app/plugins/auto_expire/plugin.py`
  - `app/plugins/cloud115/plugin.py`
  - `app/plugins/keep_alive/plugin.py`
- Keep `app/plugins/hdhive/plugin.py::_log()` because it adds behavior by
  passing `notify=False`.

## Non-Goals

- Do not change log message text, log levels, notification behavior, plugin
  scheduling, or plugin API routes.
- Do not refactor plugin business logic.

## Acceptance Criteria

- The three scoped plugins no longer define or call pure `_log()` aliases.
- `hdhive._log()` remains unchanged.
- Changed plugin files compile through `uv run`.
- The full test suite passes.
