# Refactor Notification User Bot Message Cleanup Helper

## Problem

`app/domains/notifications/user_bot_service.py` remains a large mixed-responsibility domain file. The architecture audit recommends splitting large domain files by small behavior-preserving slices.

The delayed Telegram message cleanup helper is embedded in the large service file, while it is a focused background helper used by many group command paths. Its implementation only needs runtime access to threading, sleeping, the user bot token, proxies, and the Telegram client.

## Scope

Extract `_delete_messages_later()` into a focused notification-domain module while keeping the legacy `user_bot_service._delete_messages_later()` function as a compatibility wrapper.

## Requirements

- Add a domain-local module for user bot message cleanup.
- Move the delayed deletion implementation behavior into the new module.
- Preserve the legacy wrapper signature: `_delete_messages_later(chat_id, message_ids, delay_seconds=30)`.
- Preserve daemon thread startup behavior.
- Preserve deletion behavior:
  - wait for the requested delay before deleting;
  - read the current user bot token at execution time;
  - skip deletion when token is missing;
  - skip falsy message IDs;
  - call Telegram `deleteMessage` with the same payload, proxies, and timeout;
  - swallow per-message deletion errors.
- Configure dependencies through providers so monkeypatching old `user_bot_service` globals still affects the wrapper at call time.
- Do not move command handlers or change Telegram message text in this slice.
- Add focused boundary tests for thread startup, token skip, deletion payload/proxy behavior, and swallowed deletion errors through the legacy wrapper.

## Verification

- Compile the changed modules and new tests.
- Run the focused new test file.
- Run an import check for the changed notification modules.
- Run the full test suite with `uv run pytest tests/ -v`.
