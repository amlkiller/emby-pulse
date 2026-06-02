# Weather Settings Source Contract Convergence

## Goal

Harden the weather provider setting so system weather runtime code receives a canonical, supported provider name from `app/infra/config/weather_settings.py` instead of a raw config string.

## Requirements

- Preserve existing public function names and call sites.
- Supported weather sources are `wttr`, `qweather`, and `amap`.
- `get_weather_source()` returns a canonical lowercase provider name.
- Empty, malformed, boolean, and unsupported values fall back to `wttr`.
- `set_weather_source()` persists the canonical value and falls back to `wttr` for unsupported inputs.
- Preserve existing trimming behavior for `weather_qweather_host`: runtime host strips whitespace and trailing slash, raw host preserves storage value.
- Do not change weather client requests, cache lifecycle, UI response shapes, or system router behavior beyond receiving normalized config values.

## Acceptance Criteria

- Weather source readers cannot return unsupported provider names.
- Weather source writes normalize values before persistence.
- Focused tests cover invalid, empty, boolean, supported mixed-case, and padded string values.
- Changed Python files compile.
- Focused weather settings tests and the full test suite pass through `uv run`.

## Definition of Done

- Tests added or updated for the settings contract.
- Relevant Trellis specs updated if this task records a durable pattern.
- Work changes are committed before Trellis archive and journal commits.

## Out of Scope

- Changing the weather API client implementations.
- Changing weather cache thread lifecycle.
- Changing frontend settings form options.
- Refactoring unrelated settings modules such as media server or notification settings.
- Wrapper or facade cleanup.

## Technical Notes

- `docs/架构审计.md` P3 calls out weak typed contracts in `app/infra/config/`.
- `app/domains/system/system_tools.py` branches on `qweather` and `amap`, then falls back to wttr behavior for all other values.
- `app/domains/system/router.py` exposes and saves `weather_source` through `get_weather_source()` / `set_weather_source()`.
- Existing enum normalization pattern: `app/infra/config/db_settings.py`.
