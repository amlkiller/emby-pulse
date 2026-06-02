# DB Settings Typed Contract Convergence

## Objective

Harden `app/infra/config/db_settings.py` so database-related settings expose a typed, bounded contract instead of returning raw config values.

## Scope

- Normalize `playback_data_mode` to the supported playback store modes.
- Normalize writes through `set_playback_data_mode()` so persisted values stay canonical.
- Coerce `slow_query_ms` to a positive integer with the existing default of `800`.
- Preserve existing public function names and call sites.
- Add focused regression tests for invalid, empty, differently-cased, and valid values.

## Non-Goals

- Do not change the system settings API schema.
- Do not refactor playback store or query performance logging beyond using the hardened settings contract.
- Do not perform wrapper/facade cleanup.

## Acceptance Criteria

- `get_playback_data_mode()` returns only supported canonical values.
- `set_playback_data_mode()` stores the canonical value that the getter would return.
- `get_slow_query_ms()` cannot return zero, negative numbers, booleans, or non-integer strings.
- Focused tests cover the settings contract.
- Changed files compile and the full test suite passes through `uv run`.
