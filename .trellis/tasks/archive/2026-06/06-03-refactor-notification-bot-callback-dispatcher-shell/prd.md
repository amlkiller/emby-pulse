# Refactor Notification Bot Callback Dispatcher Shell

## Goal

Continue the architecture-audit P2 domain split work by moving the Telegram callback dispatcher shell out of `app/domains/notifications/bot_service.py` into a smaller notification-domain service. `NotificationBot._handle_callback` should remain as a compatibility entrypoint but delegate permission checks, callback acknowledgement, and dispatch ordering to the new service.

## Requirements

* Extract only the `_handle_callback` dispatcher shell from `bot_service.py`.
* Preserve callback metadata extraction:
  * `data = cq.get("data", "")`;
  * `cid = str(cq["message"]["chat"]["id"])`;
  * `mid = cq["message"]["message_id"]`;
  * `cq_id = cq["id"]`.
* Preserve token/proxy lookup through the existing bot-service dynamic providers so monkeypatches remain effective.
* Preserve admin permission behavior for management callbacks:
  * `req_*` and `feed_*` require `bot._check_admin_permission(cid, user_id)`;
  * unauthorized callbacks answer with text `⛔ 您没有权限执行此操作` and `show_alert=True`;
  * Telegram answer failures are swallowed.
* Preserve normal callback acknowledgement before dispatch and swallow ACK failures.
* Preserve dispatch order:
  * plugin callback;
  * Emby restart callback;
  * request HDHive plugin callback;
  * message center callback;
  * risk ban callback;
  * feedback callback;
  * request HDHive search action;
  * request approval menu;
  * request approval action.
* Keep already extracted callback services unchanged except for provider wiring if needed.
* Add focused boundary tests for the dispatcher service covering permission rejection, normal ACK plus plugin dispatch, ACK failure swallowing, and request sub-dispatch order.

## Acceptance Criteria

* [ ] `bot_service.py` no longer owns the inline callback dispatcher body.
* [ ] A domain-local notification callback dispatcher service owns the dispatcher shell.
* [ ] `NotificationBot._handle_callback(cq)` remains available and delegates to the new service.
* [ ] Existing callback behavior and ordering are preserved.
* [ ] Focused dispatcher tests pass.
* [ ] Existing notification bot callback tests still pass.
* [ ] Full test suite passes before committing.

## Definition of Done

* Tests added or updated for the extracted dispatcher boundary.
* `uv run` is used for Python commands that execute project code.
* `git diff --check` passes.
* Code/test changes are committed separately from Trellis archive and journal commits.

## Technical Approach

Create `notification_bot_callback_dispatcher_service.py` beside the existing notification callback services. Configure it from `bot_service.py` with provider lambdas for token/proxy lookup, Telegram client, and existing callback service modules. Use lambdas that read legacy globals dynamically so tests that monkeypatch `bot_service.telegram_client` or service attributes continue to work.

## Out of Scope

* Changing any callback business behavior.
* Reordering callback handlers.
* Extracting command methods or non-callback bot methods.
* Introducing new cross-domain facades.

## Technical Notes

* Architecture audit target: `docs/架构审计.md` P2 item 5, "domain 已迁移，但内部仍是大文件混合职责".
* Current analogous pattern: `user_bot_callback_dispatcher_service.py` already owns callback dispatch for the user bot.
* This slice makes later cleanup easier by reducing `bot_service.py` to a compatibility entrypoint for callback handling.
