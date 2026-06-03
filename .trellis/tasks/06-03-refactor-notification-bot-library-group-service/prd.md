# Refactor Notification Bot Library Group Service

## Goal

Continue P2 item 5 from `docs/架构审计.md` by splitting the library notification grouping and dispatch decision logic out of `app/domains/notifications/bot_service.py`. This slice extracts `_process_library_group` behavior into a notifications-local service while preserving `SystemDaemon` as the legacy entrypoint and keeping lifecycle stop-event waits interruptible.

## Requirements

- Move item grouping and TV/movie dispatch decision behavior out of `bot_service.py` into a new domain-local service module.
- Preserve grouping keys for Episode/Season/Series/other item types.
- Preserve fresh episode lookup, fallback to series item, fallback to episode-only push, and single-item push behavior.
- Preserve per-group exception logging with the existing message format.
- Preserve the `_stop_event.wait(2)` delay/interrupt behavior for each processed group so existing shutdown behavior remains covered.
- Keep `SystemDaemon._process_library_group(items)` as the legacy wrapper.
- Add focused boundary tests for the extracted grouping behavior.

## Acceptance Criteria

- [ ] `bot_service.py` delegates `_process_library_group` to a new service while preserving stop-event wait behavior.
- [ ] New boundary tests cover grouping decisions, TV fallback branches, non-TV single-item dispatch, stop-event early return, and per-group exception logging.
- [ ] Existing bootstrap stop-hook test remains meaningful and passing.
- [ ] Focused tests pass.
- [ ] Import check passes for `bot_service.py` and the new service module.
- [ ] Full test suite passes.
- [ ] Code/test changes are committed separately from task archive and journal commits.

## Definition of Done

- Behavior-preserving refactor only; no event payload or notification behavior changes.
- No extraction of `_library_notify_loop` in this slice.
- Trellis task is archived after the code/test commit.
- Session journal records the work commit.

## Out of Scope

- Changing queue wait timing or library notify idle batching behavior.
- Changing fresh episode detection or push/publish behavior already extracted in prior slices.
- Refactoring the large `_handle_callback` method.

## Technical Notes

- Target file: `app/domains/notifications/bot_service.py`.
- Existing test `tests/test_bootstrap_stop_hooks.py` inspects `SystemDaemon._process_library_group` for `_stop_event.wait(2)` and absence of `time.sleep`; keep that lifecycle evidence intact or replace it with equivalent stronger behavior coverage.
- New service should use the same domain-local service/provider style as the existing extracted notification bot modules.
