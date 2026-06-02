# HDHiveSign Retry Wait Lifecycle Convergence

## Goal

Make HDHiveSign plugin retry delays interruptible by plugin disable so the plugin lifecycle follows the established stop-event contract.

## Requirements

* Replace the retry `time.sleep(...)` in `HDHiveSignPlugin.checkin()` with `self._stop_event.wait(...)`.
* Preserve existing retry behavior when the plugin remains enabled.
* When disable is requested during a retry delay, stop waiting and return a non-success result without recursively retrying.
* Keep the existing scheduler thread start/stop shape unchanged.
* Add focused tests for retry continuation and stop-event interruption.

## Acceptance Criteria

* [ ] `app/plugins/hdhivesign/plugin.py` no longer imports or uses `time.sleep`.
* [ ] A focused test proves retry proceeds when `_stop_event.wait(...)` returns `False`.
* [ ] A focused test proves retry is skipped when `_stop_event.wait(...)` returns `True`.
* [ ] Existing plugin scheduler lifecycle tests still pass.
* [ ] Compile checks, focused pytest, and full pytest pass through `uv run`.

## Definition of Done

* Behavior-preserving lifecycle slice is implemented.
* Tests added/updated for changed behavior.
* Trellis specs reviewed; update only if this adds new durable knowledge beyond existing lifecycle rules.
* Work commit lands before task archive and journal commits.

## Technical Approach

Patch `HDHiveSignPlugin.checkin()` so failed sign-in retries call `self._stop_event.wait(retry_interval)`. If the wait returns `True`, return the current failure message instead of invoking the recursive retry. Add tests in `tests/test_plugin_scheduler_stop_events.py` using a built plugin instance with mocked config, login, sign-in, history, and notification methods.

## Out of Scope

* HDHive resource plugin callback worker thread management.
* Broader plugin async worker cleanup.
* Wrapper/pass-through cleanup.
* External client or schema refactors.

## Technical Notes

* Audit source: `docs/架构审计.md` P1 lifecycle management.
* Relevant spec: `.trellis/spec/backend/directory-structure.md` plugin lifecycle stop-event guidance.
* Existing tests: `tests/test_plugin_scheduler_stop_events.py`.
