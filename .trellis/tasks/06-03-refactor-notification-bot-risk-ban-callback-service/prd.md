# Refactor Notification Bot Risk Ban Callback Service

## Goal

Extract the Telegram notification bot `risk_ban_` callback branch from `app/domains/notifications/bot_service.py` into a smaller notification-domain service module. This continues the architecture audit P2 item 5 work to split large mixed-responsibility domain files into maintainable, behavior-preserving slices.

## Requirements

* Add a domain-local callback service for `risk_ban_` data.
* Keep `NotificationBot._handle_callback` as the public dispatch entrypoint and delegate the risk-ban branch to the new service.
* Preserve legacy behavior:
  * non-`risk_ban_` callback data is not handled by the new service;
  * `risk_ban_<uid>` extracts the user id using the existing string replacement semantics;
  * risk service import remains lazy at callback handling time;
  * successful bans call `log_risk_action(uid, target_username, "ban", "机器快捷执法 (操作人: <operator>)")`;
  * success and failure message text remains compatible;
  * Telegram `editMessageText` failures are swallowed after the risk action attempt;
  * reply markup is cleared with an empty inline keyboard.
* Preserve existing monkeypatch compatibility by configuring dependencies from `bot_service.py` with providers that read legacy globals or bot methods dynamically.
* Add focused tests around the new service boundary.

## Acceptance Criteria

* [ ] `bot_service.py` line count is reduced and no longer contains inline `risk_ban_` business logic.
* [ ] New focused tests cover handled, not-handled, successful ban, failed ban, default operator/text fallback, and swallowed Telegram edit failures where practical.
* [ ] Focused tests pass.
* [ ] Import/compile checks for touched modules pass.
* [ ] Full test suite passes before the code commit.
* [ ] Work is committed separately from Trellis archive/journal commits.

## Definition of Done

* Tests added or updated for the extracted boundary.
* Behavior remains compatible with existing notification bot callback handling.
* No new cross-domain eager import is introduced from notification module import time.
* Trellis task is archived and session journal is recorded after code commit.

## Technical Approach

Create `app/domains/notifications/notification_bot_risk_ban_callback_service.py` with provider-based access to `telegram_client`, `ban_user`, `log_risk_action`, and the bot username lookup function. Configure the providers in `bot_service.py` using lambdas so tests and legacy monkeypatches continue to affect runtime behavior. Replace the inline `risk_ban_` branch in `_handle_callback` with a single service call.

## Decision (ADR-lite)

Context: `bot_service.py` remains a large mixed-responsibility file despite previous callback extractions. The risk-ban callback is small, isolated, and has a clear cross-domain lazy dependency on `app.domains.risk.risk_service`.

Decision: Extract only the `risk_ban_` callback into a notification-domain service and keep the existing bot dispatch contract unchanged.

Consequences: This reduces `bot_service.py` responsibility without changing the broader request approval flow. The risk service dependency remains lazy and provider-backed to avoid new import-time coupling.

## Out of Scope

* Refactoring the request approval `req_` callback flow.
* Changing risk-service ban policy or audit semantics.
* Changing Telegram callback acknowledgement behavior.
* Introducing a new cross-domain public facade in this slice.

## Technical Notes

* Architecture target: `docs/架构审计.md` P2 item 5 recommends small behavior-preserving slices for large domain files.
* Existing patterns: `notification_bot_feedback_callback_service.py`, `notification_bot_plugin_callback_service.py`, and `notification_bot_message_center_callback_service.py`.
* Primary file under reduction: `app/domains/notifications/bot_service.py`.
