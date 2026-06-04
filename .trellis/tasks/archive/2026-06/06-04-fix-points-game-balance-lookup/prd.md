# Fix points game balance lookup

## Goal

Fix points game endpoints that call the missing `point_dao.get_user_points_row()` helper by using the existing balance lookup implementation already present in `point_dao`.

## Requirements

* Replace `get_user_points_row()` usage in points game routes with the existing `get_user_points_balance()` API.
* Preserve current game behavior and response shapes.
* Do not add a duplicate DAO helper when an existing balance helper already satisfies the call sites.

## Acceptance Criteria

* [x] No application code references `point_dao.get_user_points_row()`.
* [x] Points game balance checks still compare against the configured cost.
* [x] Relevant tests pass or the reason they cannot be run is documented.

## Definition of Done

* Code uses existing domain DAO APIs.
* Targeted verification is run.
* No unrelated worktree changes are modified.

## Out of Scope

* Changing rate-limit behavior.
* Refactoring points game logic beyond replacing the missing balance lookup.

## Technical Notes

* `app/domains/points/point_dao.py` exposes `get_user_points_balance(user_id: str) -> int`.
* `app/domains/points/game_router.py` currently calls missing `get_user_points_row()` in multiple game endpoints.
