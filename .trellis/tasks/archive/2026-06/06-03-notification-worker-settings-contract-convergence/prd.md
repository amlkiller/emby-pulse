# Notification Worker Settings Contract Convergence

## Objective

Harden notification worker and queue sizing settings so background notification services receive typed, bounded integer values through a shared infra-config coercion contract.

## Scope

- Preserve existing public function names and call sites.
- Keep existing defaults and bounds:
  - `bot_worker_count`: default `8`, min `2`, max `32`.
  - `user_bot_worker_count`: default `16`, min `4`, max `50`.
  - `library_notify_queue_max`: default `300`, min `50`, max `2000`.
- Treat booleans, empty values, and malformed strings as invalid config and fall back to the setting default.
- Reuse infra-config coercion helpers instead of local `try/int/max/min` parsing.
- Add focused regression tests for invalid, valid, below-min, above-max, and boolean values.

## Non-Goals

- Do not refactor notification service worker pools or queue behavior.
- Do not change Telegram, WeCom, or user-bot runtime logic.
- Do not change API route response shapes.
- Do not perform wrapper/facade cleanup.

## Acceptance Criteria

- Worker and queue settings cannot raise on malformed config values.
- Worker and queue settings always return bounded integers.
- Existing defaults and min/max behavior are preserved.
- Focused tests cover bot worker, user-bot worker, and library queue sizing contracts.
- Changed Python files compile and the full test suite passes through `uv run`.
