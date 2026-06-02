# Notifications Bot Report Public Facade Boundary

## Goal

Move the notification bot statistics poster path off the private reports `report_service` module and through `reports.public_service`, preserving the existing stats command behavior.

## Requirements

- Replace the direct `app.domains.reports.report_service` import in `app/domains/notifications/bot_service.py` with the reports public facade.
- Preserve the existing Pillow availability check behavior.
- Preserve the existing daily poster generation behavior, including the implicit default theme used by the current `report_gen.generate_daily_poster(period, tv_list, movie_list)` call.
- Keep this task scoped to the reports facade boundary used by the notification bot stats poster path.

## Acceptance Criteria

- [x] `notifications/bot_service.py` has no direct `app.domains.reports.report_service` import.
- [x] `reports.public_service.generate_daily_poster()` supports the current three-argument notification bot call by keeping a default theme.
- [x] Notification bot stats poster generation calls `reports.public_service.has_pillow_support()`.
- [x] Notification bot stats poster generation calls `reports.public_service.generate_daily_poster(...)`.
- [x] Focused boundary tests pass.
- [x] Compile, import, private-import scan, and full pytest suite pass before commit.

## Definition of Done

- Tests added/updated for reports facade delegation and the notification bot report boundary.
- Python verification commands use `uv run`.
- Work commit is created for code/test files, followed by separate Trellis archive and journal commits.

## Technical Approach

Alias `app.domains.reports.public_service` as `report_service` in `notifications/bot_service.py`, replace `HAS_PIL` with `report_service.has_pillow_support()`, and replace direct `report_gen.generate_daily_poster(...)` with `report_service.generate_daily_poster(...)`. Update the reports public facade signature so `theme` defaults to `"cinema"`, matching the underlying report generator default and preserving the existing notification bot call shape.

## Out of Scope

- No migration of playback stats/query dependencies in `notifications/bot_service.py`.
- No changes to report image rendering, captions, query SQL, notification channels, or bot command routing.
- No split of `notifications/bot_service.py` or reports internals.

## Technical Notes

- Audit source: `docs/架构审计.md` P2 issue 6, cross-domain private import cleanup.
- Existing reports facade: `app/domains/reports/public_service.py`.
- Target files inspected:
  - `app/domains/notifications/bot_service.py`
  - `app/domains/reports/public_service.py`
  - `tests/test_reports_public_service_facade.py`
