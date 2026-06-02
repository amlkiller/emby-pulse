# Remove Calendar Notify Service Wrapper

## Goal

Remove the unused `app.domains.notifications.calendar_notify_service` middle wrapper so calendar notification lifecycle calls use the real owner module, `app.domains.notifications.calendar_notify`, directly.

## Requirements

- Delete `app/domains/notifications/calendar_notify_service.py`.
- Preserve `start_calendar_notify_services()` and `stop_calendar_notify_services()` in `app/domains/notifications/calendar_notify.py`.
- Keep `app/bootstrap/services.py` importing lifecycle hooks from `calendar_notify.py`, not from the removed wrapper.
- Add or update a regression test that fails if production code imports `calendar_notify_service`.
- Do not change calendar notification scheduling, stop behavior, config, database schema, or HTTP route behavior.

## Acceptance Criteria

- [x] `app/domains/notifications/calendar_notify_service.py` no longer exists.
- [x] No production code imports `app.domains.notifications.calendar_notify_service`.
- [x] Bootstrap lifecycle still starts and stops `calendar-notify` through `calendar_notify.py`.
- [x] Focused lifecycle/boundary tests pass.
- [x] Compile/import checks and the full pytest suite pass before commit.

## Definition of Done

- A work commit removes the wrapper and updates tests.
- The Trellis task is archived in a separate commit.
- Session journal records the work commit.

## Technical Notes

- Audit source: `docs/架构审计.md` P2 issue 6 and the backend spec rule that public/boundary modules should not be re-export bins or empty wrappers.
- Current scan found bootstrap already imports `start_calendar_notify_services` / `stop_calendar_notify_services` from `app.domains.notifications.calendar_notify`.
- The deleted wrapper exposed singular `start_calendar_notify_service()` / `stop_calendar_notify_service()` and was not referenced by app or tests.

## Out of Scope

- Renaming the existing plural lifecycle functions.
- Refactoring `CalendarNotifyService`.
- Changing service registry ordering.
