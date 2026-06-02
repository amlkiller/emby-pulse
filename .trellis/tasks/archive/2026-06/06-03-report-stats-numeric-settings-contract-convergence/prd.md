# Report and Stats Numeric Settings Contract Convergence

## Objective

Harden report and dashboard statistics numeric settings so they expose typed, bounded contracts instead of ad hoc `int(cfg.get(...))` parsing.

## Scope

- Preserve existing public function names and call sites.
- Keep existing defaults:
  - `report_top_query_limit`: `300`
  - `dashboard_cache_ttl`: `300`
- Make both readers return positive integers for empty, invalid, boolean, zero, and negative config values.
- Reuse `app.infra.config.coercion.coerce_positive_int()` instead of adding more local parsing.
- Add focused regression tests for malformed, supported, and clamped values.

## Non-Goals

- Do not change report generation, dashboard cache internals, or API response shapes.
- Do not alter route authorization or cross-domain facade boundaries.
- Do not perform wrapper/facade cleanup.

## Acceptance Criteria

- `get_report_top_query_limit()` cannot raise on malformed config.
- `get_dashboard_cache_ttl()` returns a positive integer with the existing default fallback.
- Both settings reject boolean values as invalid config and fall back to their defaults.
- Focused tests cover the settings contracts.
- Changed Python files compile and the full test suite passes through `uv run`.
