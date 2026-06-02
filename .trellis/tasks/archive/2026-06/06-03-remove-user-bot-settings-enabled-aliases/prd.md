# Remove user bot settings enabled aliases

## Goal

Remove three pure historical aliases in `app.infra.config.user_bot_settings` so callers use the canonical boolean predicates directly.

## Scope

- Replace `get_user_bot_open_reg_enabled()` with `is_user_bot_open_reg_enabled()`.
- Replace `get_user_bot_notify_user_enabled()` with `is_user_bot_open_reg_notify_user_enabled()`.
- Replace `get_user_bot_notify_group_enabled()` with `is_user_bot_open_reg_notify_group_enabled()`.
- Delete the three alias functions from `user_bot_settings.py`.

## Non-Goals

- Do not change config keys, default values, or boolean conversion semantics.
- Do not remove other config accessor functions.
- Do not alter notification/user-bot behavior.

## Acceptance

- The three alias names no longer appear under `app/` or `tests/`.
- Focused modules compile.
- Relevant tests and the full test suite pass through `uv run`.
