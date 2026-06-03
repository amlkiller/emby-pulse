# Refactor Notification User Bot New Chat Member Welcome Service

## Goal

Continue the architecture-audit P2 domain split work by moving the user bot "bot added to group" welcome-message handling out of `app/domains/notifications/user_bot_service.py` into a smaller notification-domain service. Keep `UserBot._on_new_chat_members(...)` as a compatibility entrypoint.

## Requirements

* Extract only the `_on_new_chat_members(chat_id, new_members, group_name)` welcome-message behavior.
* Preserve the existing detection logic:
  * only send a welcome when a new member is a bot;
  * compare the member id with the numeric prefix of the user bot token before `:`;
  * if the token has no `:`, compare against an empty string.
* Preserve welcome message selection:
  * use `get_user_bot_welcome_msg()` when non-empty;
  * otherwise send the existing default HTML welcome text including the group name.
* Preserve side effects:
  * call `_send(chat_id, text)`;
  * stop after the first matching bot member.
* Keep `UserBot._on_new_chat_members(...)` available and delegate to the extracted service.
* Configure dependencies from `user_bot_service.py` via provider lambdas so tests and legacy monkeypatches remain effective.
* Add focused boundary tests for custom welcome, default welcome, non-matching members, and stop-after-first-match behavior.

## Acceptance Criteria

* [ ] `user_bot_service.py` no longer owns the full new-chat-member welcome body.
* [ ] A domain-local notification service owns that behavior.
* [ ] `UserBot._on_new_chat_members(...)` remains callable and behavior-compatible.
* [ ] Focused tests pass for the extracted service.
* [ ] Existing notification user bot tests still pass.
* [ ] Full test suite passes before committing.

## Definition of Done

* Tests added or updated for the extracted boundary.
* `uv run` is used for Python commands that execute project code.
* `git diff --check` passes.
* Code/test changes are committed separately from Trellis archive and journal commits.

## Technical Approach

Create `app/domains/notifications/user_bot_new_chat_member_service.py` with a boolean/void handler and provider wiring for token, welcome message, and send function. Replace the class method body in `user_bot_service.py` with a delegation wrapper.

## Out of Scope

* Changing user bot polling or scheduler lifecycle.
* Changing Telegram update dispatch.
* Changing command registration.
* Reworking group restriction or channel binding behavior.

## Technical Notes

* Architecture audit target: `docs/架构审计.md` P2 item 5, "domain 已迁移，但内部仍是大文件混合职责".
* Current file: `app/domains/notifications/user_bot_service.py`, still one of the largest domain files after prior extracts.
* This is intentionally a small behavior-preserving slice because the lifecycle code has detailed existing stop/restart tests.
