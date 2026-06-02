# Remove Notification DAO Short Alias

## Goal

Remove the pure `app.infra.db.notification_dao.add_sys_notification()` alias so
callers use the real notification persistence function directly:
`add_system_notification()`.

## Scope

- Replace imports and calls that target
  `app.infra.db.notification_dao.add_sys_notification` with
  `add_system_notification`.
- Remove the pure alias from `app/infra/db/notification_dao.py`.
- Update tests that monkeypatch or assert the old DAO alias name.

## Non-Goals

- Do not change notification payloads, route responses, or rule ordering.
- Do not remove `app.infra.db.database.add_sys_notification`; that function
  wraps `add_system_notification()` with error logging and is not a pure alias.
- Do not migrate unrelated DAO functions.

## Acceptance Criteria

- No production caller imports or calls
  `notification_dao.add_sys_notification`.
- `notification_dao.py` exposes only `add_system_notification` for this write.
- Tests refer to the real function name where they patch or assert this path.
- Changed Python files compile with `uv run`.
- The full test suite passes.
