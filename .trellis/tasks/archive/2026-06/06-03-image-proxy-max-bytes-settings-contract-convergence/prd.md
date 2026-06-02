# Image Proxy Max Bytes Settings Contract Convergence

## Goal

Harden the image proxy per-image cache size setting so proxy runtime code receives a typed, positive integer value through `app/infra/config/image_proxy_settings.py` instead of ad hoc `int(cfg.get(...))` parsing.

## Requirements

- Preserve the public function name `get_image_proxy_max_bytes()`.
- Preserve the existing default of `10 * 1024 * 1024` bytes.
- Treat booleans, empty values, missing values, malformed strings, and `None` as invalid config and return the default.
- Clamp zero and negative numeric values to the minimum positive value of `1`.
- Reuse the shared `app.infra.config.coercion.coerce_positive_int()` helper rather than local parsing.
- Do not change image proxy route URLs, response shapes, streaming behavior, cache eviction policy, or media/TMDB fallback logic.

## Acceptance Criteria

- The image proxy max-bytes setting cannot raise on malformed config values.
- The reader always returns an `int`.
- The reader returns the default for invalid/boolean/empty values.
- The reader returns `1` for zero or negative numeric values.
- Focused regression tests cover default, valid string/int, invalid, boolean, zero, and negative values.
- Changed Python files compile and the full test suite passes through `uv run`.

## Definition of Done

- Focused tests added for the settings contract.
- Relevant specs reviewed and updated only if a new durable convention is introduced.
- Work changes are committed before Trellis archive and journal commits.

## Out of Scope

- Adding a UI writer for `image_proxy_max_bytes`.
- Changing the 10MB default.
- Adding an upper bound for image proxy cache size without product input.
- Refactoring proxy router cache behavior.
- Wrapper or facade cleanup.

## Technical Notes

- `docs/架构审计.md` P3 calls out weak typed contracts in `app/infra/config/`.
- `app/core/config.py` defines `image_proxy_max_bytes` as `10 * 1024 * 1024`.
- `app/domains/proxy/router.py` uses `get_image_proxy_max_bytes()` to reject oversized cached image streams.
- Existing positive integer helper: `app.infra.config.coercion.coerce_positive_int()`.
