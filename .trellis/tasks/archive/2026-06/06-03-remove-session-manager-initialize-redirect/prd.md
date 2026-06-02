# Remove Session Manager Initialize Redirect

## Goal

Remove the pure redirect inside `SessionManager` so the public initialization method contains the actual table initialization logic.

## Scope

- Inline the `_ensure_init()` body into `SessionManager.initialize()`.
- Update internal callers that used `_ensure_init()` to call `initialize()` instead.
- Delete `_ensure_init()`.
- Preserve session table creation behavior and idempotency.
- Do not change session cleanup startup, DAO functions, or configuration/data accessors.

## Acceptance Criteria

- `SessionManager.initialize()` ensures the session table once and records `_initialized`.
- `get_or_create_session()` still initializes before reading or creating sessions.
- No references to `_ensure_init` remain.
- Focused tests and the full test suite pass.
