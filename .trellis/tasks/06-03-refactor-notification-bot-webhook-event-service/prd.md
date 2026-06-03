# Refactor Notification Bot Webhook Event Service

## Goal

Continue the architecture-audit refactor by extracting `SystemDaemon.on_webhook_event()` from the large `bot_service.py` file into a focused notification-domain service module. Preserve webhook event routing, library task enqueueing, calendar/gap side effects, bus publication, and the legacy `SystemDaemon.on_webhook_event()` entry point.

## Requirements

* Add a notification-domain module responsible for notification daemon webhook event routing.
* Move `SystemDaemon.on_webhook_event()` implementation into the new module.
* Keep `SystemDaemon.on_webhook_event()` as a compatibility wrapper.
* Preserve important-event logging only when the event contains any of:
  `item.added`, `library.new`, `playback.start`, `playback.stop`, `auth`, `login`, `delete`, `remove`.
* Preserve log text: `🔔 [Webhook] 收到事件: {event}`.
* Preserve `item.added` / `library.new` handling:
  * Read `item = data.get("Item", {})`.
  * If `item.get("Id")`, call `daemon.add_library_task(item)`.
  * If the item type is `Episode`, dynamically import `app.domains.playback.calendar_service.calendar_service`.
  * Call `calendar_service.mark_episode_ready(item.get("SeriesId"), item.get("ParentIndexNumber"), item.get("IndexNumber"))`.
  * Call `daemon._clear_gap_record_async(item)`.
* Preserve `playback.start` handling:
  * Log `🔔 [Webhook] 发布 playback.start 事件`.
  * Publish `bus.publish("notify.playback.start", data)`.
* Preserve `playback.stop` handling:
  * Log `🔔 [Webhook] 发布 playback.stop 事件`.
  * Publish `bus.publish("notify.playback.stop", data)`.
* Preserve auth/login handling by publishing `notify.user.login`.
* Preserve delete/remove handling by publishing `notify.item.deleted`.
* Preserve the existing `elif` ordering.
* Use lazy providers for legacy globals so monkeypatches on `bot_service` remain effective.

## Acceptance Criteria

* [ ] `bot_service.py` line count is reduced by moving webhook event routing into a new domain-local module.
* [ ] `SystemDaemon.on_webhook_event()` delegates to the new service.
* [ ] Important webhook events keep the existing receive log; unimportant events do not log.
* [ ] Library item events enqueue items only when an item id exists.
* [ ] Episode library events also mark the calendar episode ready and clear gap records.
* [ ] Playback start/stop publish the existing notification event names and keep the existing publish logs.
* [ ] Auth/login events publish `notify.user.login`.
* [ ] Delete/remove events publish `notify.item.deleted`.
* [ ] Focused webhook event tests pass.
* [ ] Full test suite passes before code commit.

## Definition of Done

* Tests added for the extracted webhook event boundary.
* Focused compile/import verification passes.
* Focused tests and full tests pass through `uv run`.
* Work commit is separate from Trellis archive and journal commits.

## Technical Approach

Create `app/domains/notifications/notification_bot_webhook_event_service.py` with `handle_webhook_event(daemon, event, data)`. Configure providers from `bot_service.py` for `bus`, logger, and calendar-service lookup. Keep `SystemDaemon.on_webhook_event()` as a thin wrapper.

## Decision (ADR-lite)

**Context**: `bot_service.py` still contains webhook routing logic inside the daemon class, mixed with queueing, request completion, and scheduler behavior.

**Decision**: Extract only webhook event routing in this slice. Leave library task queueing/group processing and gap clearing implementations for later slices.

**Consequences**: Webhook event routing becomes independently testable and `bot_service.py` shrinks without changing event names or side effects.

## Out of Scope

* Changing webhook event names or matching semantics.
* Changing library queue behavior.
* Changing calendar or gap clearing implementation.
* Changing playback/user/item notification handlers.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Current target: `app/domains/notifications/bot_service.py`.
* Existing extraction pattern: notification bot named service modules with lazy dependency providers and legacy wrappers.
