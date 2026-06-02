# Remove Notification Episode Zfill Redirect

## Goal

Remove the local `zf()` helper in `NotificationBot.on_library_new_episode()` because it only redirects to `str(num).zfill(2)`.

## Scope

- Replace local `zf(...)` call sites with direct `str(...).zfill(2)`.
- Delete the local `zf()` helper.
- Preserve episode and season formatting output exactly.
- Do not change notification delivery, template logic, configuration access, or event handling.

## Acceptance Criteria

- No `zf()` local helper remains in `on_library_new_episode()`.
- New episode notification formatting still zero-pads season and episode numbers.
- Focused compile/import checks and the full test suite pass.
