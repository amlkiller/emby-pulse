# Calendar Settings TTL Contract Convergence

## Objective

Harden `app/infra/config/calendar_settings.py` so calendar cache TTL reads and writes expose a typed, bounded settings contract instead of raw config passthrough.

## Scope

- Preserve existing public functions and call sites.
- Keep the existing default TTL of `86400` seconds.
- Make `get_calendar_cache_ttl()` return a positive integer for empty, invalid, boolean, zero, and negative config values.
- Make `set_calendar_cache_ttl()` persist the same normalized positive integer that readers return.
- Preserve `get_calendar_public_url()` behavior.
- Add a small infra-config numeric coercion helper rather than duplicating the same positive-integer parsing pattern again.
- Add focused regression tests for reader and writer normalization.

## Non-Goals

- Do not change calendar API routes or response shapes.
- Do not refactor calendar service lifecycle or cache internals in this slice.
- Do not perform wrapper/facade cleanup.

## Acceptance Criteria

- Calendar TTL reads cannot crash on malformed config values.
- Calendar TTL reads never return zero, negative numbers, booleans, or non-integer strings.
- Calendar TTL writes normalize before persistence.
- Focused tests cover the settings contract.
- Changed Python files compile and the full test suite passes through `uv run`.
