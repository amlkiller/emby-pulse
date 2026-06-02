# Remove Points Config Router Alias

## Goal

Remove the `points.router.get_point_config` middle alias and point callers at the real configuration owner, `app.domains.points.point_dao.get_point_config`.

## Requirements

- Delete `get_point_config = point_dao.get_point_config` from `app/domains/points/router.py`.
- Replace in-module uses of `get_point_config()` in `points.router` with `point_dao.get_point_config()`.
- Replace `notifications.bot` import from `app.domains.points.router` with direct use of `app.domains.points.point_dao.get_point_config()`.
- Do not add any new wrapper/facade/public_service function.
- Preserve points config values, lottery pool behavior, auth checks, and response payloads.
- Add or update tests that prevent notification code from importing `points.router` for this config lookup.

## Acceptance Criteria

- [x] `app/domains/points/router.py` no longer exposes `get_point_config` as a module alias.
- [x] No production code imports `get_point_config` from `app.domains.points.router`.
- [x] `notifications.bot.api_lottery_pool()` reads config from `point_dao.get_point_config()`.
- [x] Focused tests cover the direct DAO owner lookup and existing points page boundary behavior.
- [x] Compile/import checks, alias-removal scan, focused tests, and full pytest suite pass.

## Definition of Done

- Work commit contains only code/test changes for this slice.
- Trellis task archive commit is separate.
- Journal records the work commit.

## Technical Notes

- Audit source: `docs/架构审计.md` P2 issue 6, reducing cross-domain direct imports.
- This follows the current user direction: do not introduce wrappers; use the real implementation owner directly.
- `points.router.get_point_config` is a simple alias to `point_dao.get_point_config`, so removing it does not change behavior.

## Out of Scope

- Broader points router decomposition.
- Notification bot lottery behavior changes.
- Moving points DAO functions.
