# Refactor Notification User Bot Menu Helpers

## Problem

`app/domains/notifications/user_bot_service.py` remains a large mixed-responsibility domain file. The architecture audit recommends splitting large domain files by behavior-preserving slices instead of large rewrites.

The user bot main menu keyboard builder is a narrow UI helper currently embedded in the large service file. It is used by command handlers but only depends on the configured portal URL.

## Scope

Extract the user bot main menu keyboard builder into a focused notification-domain module while keeping the legacy `_main_menu_keyboard()` function in `user_bot_service.py` as a compatibility wrapper.

## Requirements

- Add a domain-local module for user bot menu helpers.
- Move the `_main_menu_keyboard()` implementation behavior into the new module.
- Preserve the exact keyboard structures, callback data, text labels, and portal URL behavior.
- Keep `user_bot_service._main_menu_keyboard(binding=None)` available for existing callers and tests.
- Configure dependencies through providers so monkeypatching `user_bot_service.get_user_bot_portal_url` still affects the wrapper at call time.
- Do not move command handlers or change Telegram message text in this slice.
- Add focused boundary tests for unbound menu, bound menu without portal URL, and bound menu with portal URL through the legacy wrapper.

## Verification

- Compile the changed modules and new tests.
- Run the focused new test file.
- Run the full test suite with `uv run pytest tests/ -v`.
