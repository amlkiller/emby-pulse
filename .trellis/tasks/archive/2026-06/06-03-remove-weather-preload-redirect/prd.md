# Remove Weather Preload Redirect

## Goal

Remove `preload_weather_cache()` because it only forwards to `start_weather_cache_refresh()`.

## Scope

- Update bootstrap runtime to import and call `start_weather_cache_refresh()` directly.
- Delete `preload_weather_cache()` from `app/domains/system/system_tools.py`.
- Preserve the startup delay and background-thread orchestration in runtime.
- Do not change weather cache refresh behavior or weather configuration accessors.

## Acceptance Criteria

- No `preload_weather_cache()` definition or call remains.
- Weather cache background refresh still starts through the bootstrap delayed startup path.
- Focused compile/import checks and the full test suite pass.
