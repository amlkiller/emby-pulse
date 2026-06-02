# Remove Plugin Config Refresh Alias

## Goal

Remove the `PluginBase._refresh_config_cache()` alias because it only forwards
to the real cache-loading implementation, `PluginBase._load_config_to_cache()`.

## Scope

- Replace the only internal caller in
  `app/plugins/season_poster_updater/plugin.py` with `_load_config_to_cache()`.
- Delete `PluginBase._refresh_config_cache()` from `app/plugins/base.py`.

## Non-Goals

- Do not change plugin config persistence, cache contents, route responses, or
  plugin lifecycle behavior.
- Do not rename `_load_config_to_cache()`.

## Acceptance Criteria

- No production code references `_refresh_config_cache`.
- Tests and plugin code continue using `_load_config_to_cache()` where they need
  to bypass or refresh cached plugin config.
- Changed Python files compile with `uv run`.
- The full test suite passes.
