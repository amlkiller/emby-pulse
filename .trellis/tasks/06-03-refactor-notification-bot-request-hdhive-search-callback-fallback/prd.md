# Refactor Notification Bot Request HDHive Search Callback Fallback

## Goal

Continue the architecture-audit P2 domain split work by moving the `req_hdhive_*` search action fallback handling out of `app/domains/notifications/bot_service.py` into a smaller notification-domain callback service. This should reduce mixed responsibilities in `bot_service.py` without changing Telegram callback behavior.

## Requirements

* Extract only the request HDHive search action branch currently handled inline by `NotificationBot._handle_callback`.
* Preserve the existing callback data contract for `req_hdhive_<tmdb_id>_<media_type>_...` actions.
* Preserve successful delegation to `app.plugins.hdhive.plugin.handle_request_hdhive_search(data, cid, cq_id, "tg")`.
* Preserve the existing failure behavior:
  * log `[Bot] 影巢搜索回调处理失败: <error>`;
  * clear the message inline keyboard with Telegram `editMessageReplyMarkup`;
  * swallow Telegram cleanup errors.
* Keep existing `bot_service.py` compatibility wrappers and provider wiring style consistent with the nearby extracted callback services.
* Add focused boundary tests for handled/non-handled data, successful plugin delegation, plugin failure fallback, and Telegram cleanup failure swallowing.

## Acceptance Criteria

* [ ] `bot_service.py` no longer contains the inline `req_hdhive` search fallback block.
* [ ] A domain-local notification callback service owns that behavior.
* [ ] Existing plugin callback handling in `notification_bot_plugin_callback_service.py` remains behavior-compatible.
* [ ] Focused tests pass for the new service.
* [ ] Existing notification bot callback tests still pass.
* [ ] Full test suite passes before committing.

## Definition of Done

* Tests added or updated for the extracted boundary.
* `uv run` is used for Python commands that execute project code.
* `git diff --check` passes.
* Code/test changes are committed separately from Trellis archive and journal commits.

## Technical Approach

Create a small service beside the existing notification bot callback services. Configure its dependencies from `bot_service.py` using provider lambdas so tests and legacy monkeypatches can still replace `bot_service.telegram_client` and `bot_service.logger` dynamically. Replace the inline branch in `_handle_callback` with a boolean-returning service call.

## Out of Scope

* Changing HDHive plugin internals.
* Reworking the full `_handle_callback` dispatcher.
* Changing request approval menu/action behavior.
* Introducing a cross-domain public facade in this slice.

## Technical Notes

* Architecture audit target: `docs/架构审计.md` P2 item 5, "domain 已迁移，但内部仍是大文件混合职责".
* Current pattern references: `notification_bot_request_approval_menu_callback_service.py`, `notification_bot_request_approval_action_callback_service.py`, and their boundary tests.
* Keep this as a behavior-preserving slice to make later dispatcher extraction easier.
