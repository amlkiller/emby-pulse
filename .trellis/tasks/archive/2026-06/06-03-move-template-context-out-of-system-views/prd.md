# Move Template Context Out Of System Views

## Goal

Remove cross-domain imports of `app.domains.system.views.get_common_vars` by moving the real template context implementation to a shared owner and pointing all callers directly at that owner.

## Requirements

- Add `app/shared/view_context.py` as the real implementation owner for `get_common_vars(request, active_page, extra_vars=None)`.
- Move the existing behavior from `app/domains/system/views.py` into `app/shared/view_context.py` without changing returned context fields or fallback behavior.
- Update `app/domains/system/views.py`, `app/domains/points/router.py`, `app/domains/plugins/router.py`, and `app/domains/playback/calendar.py` to import `get_common_vars` directly from `app.shared.view_context`.
- Do not leave a `get_common_vars` wrapper in `system.views`.
- Do not introduce any new `public_service.py`, facade, or wrapper function.
- Preserve page auth ordering: unauthenticated/unauthorized paths must not build template context.
- Preserve template names and response context data.

## Acceptance Criteria

- [x] `app/domains/system/views.py` no longer defines `get_common_vars`.
- [x] No app code imports `get_common_vars` from `app.domains.system.views`.
- [x] Points, plugins, playback calendar, and system views import `get_common_vars` from `app.shared.view_context`.
- [x] Focused tests cover the direct shared owner import and preserve auth-before-template-context behavior.
- [x] Compile/import checks, boundary scan, focused tests, and full pytest suite pass.

## Definition of Done

- Work commit contains the shared owner move and tests only.
- Trellis task archive commit is separate.
- Journal records the work commit.

## Technical Notes

- Audit source: `docs/架构审计.md` P2 issue 6 about reducing cross-domain direct imports, plus the backend spec rule to avoid deepening cross-domain imports.
- This is not a new wrapper. `app.shared.view_context.get_common_vars` becomes the real implementation owner.
- `get_common_vars` currently depends on shared version, infra config, and `media_api`; it does not need `system.views` route ownership.

## Out of Scope

- Refactoring page permission helpers in `system.views`.
- Changing template rendering or Jinja setup.
- Changing media server settings, Pro state, or session field semantics.
