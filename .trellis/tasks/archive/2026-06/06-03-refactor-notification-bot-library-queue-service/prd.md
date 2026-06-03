# Refactor Notification Bot Library Queue Service

## Goal

Continue the architecture-audit refactor by extracting `SystemDaemon.add_library_task()` from the large `bot_service.py` file into a focused notification-domain service module. Preserve library notification queue behavior and keep the legacy `SystemDaemon.add_library_task()` entry point.

## Requirements

* Add a notification-domain module responsible for enqueueing library notification tasks.
* Move `add_library_task()` implementation into the new module.
* Keep `SystemDaemon.add_library_task()` as a compatibility wrapper.
* Preserve use of `daemon.library_lock` to guard the queue mutation.
* Preserve the current local fallback assignment `max_queue = 300` before reading configured max.
* Preserve configured max lookup through `get_library_notify_queue_max()`.
* Preserve dropping the oldest item when `len(daemon.library_queue) >= max_queue`.
* Preserve warning log text: `[入库通知] 队列已满，丢弃最旧项目: {dropped.get("Name") or dropped.get("Id")}`.
* Preserve dedupe by item id: append only when no existing queued item has the same `Id`.
* Preserve behavior for missing `Id` exactly as the current `x.get("Id") == item.get("Id")` check behaves.
* Use lazy providers for legacy globals so monkeypatches on `bot_service` remain effective.

## Acceptance Criteria

* [ ] `bot_service.py` line count is reduced by moving library queue enqueueing into a new domain-local module.
* [ ] `SystemDaemon.add_library_task()` delegates to the new service.
* [ ] Items are appended while under the configured queue limit.
* [ ] Duplicate item ids are skipped.
* [ ] When at capacity, the oldest item is dropped and the existing warning log is emitted.
* [ ] Missing item ids follow the existing dedupe semantics.
* [ ] Queue mutation remains protected by `daemon.library_lock`.
* [ ] Focused library queue tests pass.
* [ ] Full test suite passes before code commit.

## Definition of Done

* Tests added for the extracted library queue boundary.
* Focused compile/import verification passes.
* Focused tests and full tests pass through `uv run`.
* Work commit is separate from Trellis archive and journal commits.

## Technical Approach

Create `app/domains/notifications/notification_bot_library_queue_service.py` with `add_library_task(daemon, item)`. Configure providers from `bot_service.py` for `get_library_notify_queue_max` and `logger`. Keep `SystemDaemon.add_library_task()` as a thin wrapper.

## Decision (ADR-lite)

**Context**: `bot_service.py` still contains library notification queue mutation logic inside the daemon class.

**Decision**: Extract only queue enqueueing in this slice. Leave `_library_notify_loop()` and `_process_library_group()` for later slices.

**Consequences**: Library queue behavior becomes independently testable and `bot_service.py` shrinks without changing scheduling, grouping, or notification behavior.

## Out of Scope

* Changing queue size settings.
* Changing queue drain timing.
* Changing library item grouping or notification publishing.
* Changing lock type or daemon lifecycle behavior.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Current target: `app/domains/notifications/bot_service.py`.
* Existing extraction pattern: notification bot named service modules with lazy dependency providers and legacy wrappers.
