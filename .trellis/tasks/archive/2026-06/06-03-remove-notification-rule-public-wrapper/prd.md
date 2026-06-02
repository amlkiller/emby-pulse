# Remove Notification Rule Public Wrapper

## Goal

Remove the redundant `notifications.public_service.get_notify_rule()` wrapper and point callers at the module that actually owns notification rule lookup, preserving notification rule behavior.

## Requirements

- Delete `get_notify_rule()` from `app/domains/notifications/public_service.py`.
- Replace callers that use `notification_service.get_notify_rule(...)` with `app.domains.notifications.notify_admin.get_notify_rule(...)`.
- Preserve notify type strings, rule lookup ordering, channel checks, send behavior, logging, and fallback behavior.
- Keep notification send/user-bot facade functions in `notifications.public_service.py`; they add lazy runtime lookup and external send boundary value.
- Update tests that asserted the removed wrapper exists or that callers avoid `notify_admin`.

## Acceptance Criteria

- [x] `notifications.public_service` no longer exposes `get_notify_rule()`.
- [x] Media request notification rule lookups import and call `notifications.notify_admin.get_notify_rule()` directly.
- [x] User delete notification rule lookup imports and calls `notifications.notify_admin.get_notify_rule()` directly.
- [x] Focused tests prove rule lookup still happens before notification sends or side effects.
- [x] Compile, import, wrapper-removal scan, and full pytest suite pass before commit.

## Definition of Done

- Tests updated for direct `notify_admin` rule lookup and removal of the pure wrapper assertion.
- Python verification commands use `uv run`.
- Work commit is created for code/test files, followed by separate Trellis archive and journal commits.

## Technical Approach

Import `app.domains.notifications.notify_admin` in affected callers as the rule lookup owner, replace only `get_notify_rule()` calls, and keep `notifications.public_service` for semantic notification sending methods such as bot sends and user-bot sends.

## Out of Scope

- No migration of notification sending facade methods.
- No changes to rule storage, notify type names, channels, message text, platforms, or notification DAO behavior.
- No broader notification router/service split.

## Technical Notes

- Audit source: `docs/架构审计.md` P2 issue 6, plus current backend spec guidance that public service modules are semantic boundaries, not re-export bins.
- Existing real rule lookup owner: `app/domains/notifications/notify_admin.py`.
- Target callers discovered:
  - `app/domains/media_requests/router.py`
  - `app/domains/users/router.py`
  - tests covering notification rule boundary behavior.
