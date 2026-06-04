# Fix TG Points Shop Items

## Goal

Fix the Telegram user bot points shop so `/shop` displays configured store items instead of reporting an empty shop when items are returned under the current user points API shape.

## Requirements

* Keep the existing Web user points response shape unchanged.
* Update the Telegram shop command to read store items from `points_info["config"]["store_items"]`.
* Preserve compatibility with any callers/tests that still provide top-level `points_info["store_items"]`.
* Keep the empty-shop response when no store items exist.

## Acceptance Criteria

* [x] `cmd_shop` renders items returned under `config.store_items`.
* [x] Existing top-level `store_items` behavior still works.
* [x] Empty store still returns the existing "积分商城暂无商品" response.
* [x] Relevant user bot shop tests pass.

## Definition of Done

* Tests added or updated for the nested config path.
* Targeted tests pass through `uv run`.
* No unrelated code or data changes.

## Technical Approach

Resolve store items in `app/bot/user_bot/user_bot_shop_commands_service.py` through a small compatibility helper or local fallback:
prefer top-level `store_items` when present, otherwise use nested `config.store_items`.

## Out of Scope

* Changing Web user community/store APIs.
* Backfilling production database `point_config.store_items`.
* Redesigning points config serialization.

## Technical Notes

* `app/domains/points/point_dao.py#get_user_points_info` parses `store_items` and returns it under `config`.
* `app/bot/user_bot/user_bot_shop_commands_service.py#cmd_shop` currently reads top-level `store_items`.
* `tests/test_notification_user_bot_shop_commands_service_boundary.py` covers TG shop rendering and empty store paths.
* Verification passed: `uv run python -m compileall app/bot/user_bot/user_bot_shop_commands_service.py tests/test_notification_user_bot_shop_commands_service_boundary.py`.
* Verification passed: `uv run pytest tests/test_notification_user_bot_shop_commands_service_boundary.py -v`.
* Verification passed: `uv run pytest tests/ -v` (`920 passed, 3 warnings`).
* Verification passed: `git diff --check`.
