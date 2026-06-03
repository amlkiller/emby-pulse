# Refactor Notification Bot Auto Finish Request Service

## Goal

Continue the architecture-audit refactor by extracting `SystemDaemon._auto_finish_request()` and its status-change notification helper from the large `bot_service.py` file into a focused notification-domain service module. Preserve automatic media-request completion and user notification behavior while keeping the legacy `SystemDaemon` entry points.

## Requirements

* Add a notification-domain module responsible for automatic media-request finish handling.
* Move `_auto_finish_request()` implementation into the new module.
* Move `_notify_request_status_change()` implementation into the same new module because it is the direct notification helper for auto-finish.
* Keep `SystemDaemon._auto_finish_request()` and `SystemDaemon._notify_request_status_change()` as compatibility wrappers.
* Preserve early return when `tmdb_id` is empty.
* Preserve `tid = int(tmdb_id)` conversion.
* Preserve `media_request_dao.finish_media_requests_for_item(tid, season)` call.
* Preserve notification only when both `requests_to_notify` and `users_to_notify` are truthy.
* Preserve auto-finish error logging: `[自动入库] 更新工单状态失败: {e}`.
* Preserve status notification rule lookup through `app.domains.notifications.notify_admin.get_notify_rule("request_status")`.
* Preserve rule guard: no notification unless rule exists, `enabled` is truthy, and `"tg_bot"` is in `channels`.
* Preserve disabled-rule info log: `[状态变更通知] 规则未启用或渠道不含tg_bot`.
* Preserve `media_request_dao.list_tg_bindings(user_ids)` lookup.
* Preserve dynamic import of `app.domains.notifications.user_bot_service._send` and `_tg_api`.
* Preserve request title formatting: TV uses `"{title} S{season}"`, non-TV uses `title`.
* Preserve all existing status icon/text branches for `approve`, `finish`, `reject`, `manual`, `hdhive_done`, and default.
* Preserve message text format.
* Preserve per-user send only when a Telegram binding exists.
* Preserve send log: `[自动入库通知] 发送给用户: tg_id={tg_id}, title={title_text}`.
* Preserve per-send failure logging: `[自动入库通知] 发送失败: {e}`.
* Preserve outer notification failure logging: `[状态变更通知] 通知失败: {e}`.
* Use lazy providers for legacy globals so monkeypatches on `bot_service` remain effective.

## Acceptance Criteria

* [ ] `bot_service.py` line count is reduced by moving auto-finish and request-status notification handling into a new domain-local module.
* [ ] `SystemDaemon._auto_finish_request()` delegates to the new service.
* [ ] `SystemDaemon._notify_request_status_change()` delegates to the new service.
* [ ] Empty TMDB IDs skip DAO and notification side effects.
* [ ] Valid TMDB IDs call finish DAO with integer TMDB ID and season.
* [ ] Finish notifications are sent only when both request and user lists are present.
* [ ] Disabled/missing notification rule skips sends and logs the existing info message.
* [ ] Telegram bindings are looked up for all users and only bound users receive messages.
* [ ] Existing action text/icon branches and message format are preserved.
* [ ] Per-send and outer errors are logged and swallowed.
* [ ] Focused auto-finish tests pass.
* [ ] Full test suite passes before code commit.

## Definition of Done

* Tests added for the extracted auto-finish and request-status notification boundary.
* Focused compile/import verification passes.
* Focused tests and full tests pass through `uv run`.
* Work commit is separate from Trellis archive and journal commits.

## Technical Approach

Create `app/domains/notifications/notification_bot_auto_finish_request_service.py` with `auto_finish_request(bot, tmdb_id, season=None)` and `notify_request_status_change(tmdb_id, requests_info, users_info, action, reject_reason=None)`. Configure providers from `bot_service.py` for media request DAO, logger, notify-rule lookup, and user bot service send lookup. Keep `SystemDaemon` methods as thin wrappers.

## Decision (ADR-lite)

**Context**: `bot_service.py` still contains media-request completion and user notification orchestration inside the daemon class.

**Decision**: Extract only the auto-finish/status-notification pair in this slice. Leave library event grouping, gap clearing, and webhook routing for later slices.

**Consequences**: Request completion notification behavior becomes independently testable and `bot_service.py` shrinks without changing media request DAO contracts or Telegram message text.

## Out of Scope

* Changing media request DAO contracts.
* Changing notification rule semantics.
* Changing Telegram message text, parse mode, or delivery implementation.
* Changing library event queue/group handling.
* Changing webhook routing.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Current target: `app/domains/notifications/bot_service.py`.
* Existing extraction pattern: notification bot named service modules with lazy dependency providers and legacy wrappers.
