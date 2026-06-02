# User Bot Registration Settings Contract Convergence

## Objective

Harden registration-related `app/infra/config/user_bot_settings.py` readers and writers so user bot registration behavior receives normalized, bounded settings instead of raw config values.

## Scope

- Preserve existing public function names and call sites.
- Normalize `user_bot_reg_quota_mode` to supported canonical values: `total` and `batch`.
- Normalize `user_bot_route_mode` to supported canonical values: `block` and `allow`.
- Normalize writes through the existing enum setters before persistence.
- Bound registration-related integer settings:
  - `user_bot_reg_batch_used`: non-negative integer, default `0`; writes normalize before persistence.
  - `user_bot_reg_quota`: non-negative integer, default `0`.
  - `user_bot_max_reg`: non-negative integer, default `0`.
  - `user_bot_reg_days`: positive integer, default `30`.
- Preserve existing worker count and restriction cache TTL behavior unless needed for shared helper use.
- Add focused regression tests for invalid, empty, case/whitespace, supported, clamped, and writer-normalized values.

## Non-Goals

- Do not refactor `user_bot_service.py` registration flow or concurrency logic.
- Do not change bot API route response shapes.
- Do not change notification behavior or Telegram integration.
- Do not perform wrapper/facade cleanup.

## Acceptance Criteria

- Registration quota mode and route mode readers return only supported canonical values.
- Enum setters persist canonical values.
- Registration integer readers cannot raise on malformed config and return bounded integers.
- `set_user_bot_registration_batch_used()` normalizes before persistence.
- Focused tests cover the settings contract.
- Changed Python files compile and the full test suite passes through `uv run`.
