# Refactor Notification Bot Library Push Service

## Goal

Continue P2 item 5 from `docs/架构审计.md` by splitting the library notification push/publish responsibility out of `app/domains/notifications/bot_service.py`. This slice extracts `_push_episode_group` and `_push_single_item` behavior into a notifications-local service while preserving the existing `SystemDaemon` wrapper methods and event payloads.

## Requirements

- Move episode-group push behavior out of `bot_service.py` into a new domain-local service module.
- Move single-item push behavior out of `bot_service.py` into the same service module.
- Preserve existing media detail refresh behavior, status-code checks, fallback data behavior, TMDB auto-finish calls, cleared-gap deletion and `notify.gap_cleared` publication, and `notify.library.*` event payloads.
- Keep `SystemDaemon._push_episode_group` and `_push_single_item` wrappers for existing internal callers and monkeypatch compatibility.
- Configure service dependencies from `bot_service.py` with dynamic providers for legacy globals such as `get_admin_id`, `media_api`, `gap_dao`, and `bus`.
- Add focused boundary tests for the extracted push behavior.

## Acceptance Criteria

- [ ] `bot_service.py` delegates `_push_episode_group` and `_push_single_item` to the new service.
- [ ] New boundary tests cover detail refresh success/fallback, gap-clear publication, per-season auto-finish calls, single-item auto-finish, and swallowed dependency errors.
- [ ] Focused tests pass.
- [ ] Import check passes for `bot_service.py` and the new service module.
- [ ] Full test suite passes.
- [ ] Code/test changes are committed separately from task archive and journal commits.

## Definition of Done

- Behavior-preserving refactor only; no notification payload or event-name changes.
- No broad extraction of `_process_library_group` or `_library_notify_loop` in this slice.
- Trellis task is archived after the code/test commit.
- Session journal records the work commit.

## Out of Scope

- Extracting `_process_library_group` grouping decisions.
- Changing auto-finish request semantics.
- Introducing new cross-domain public facades in this slice.

## Technical Notes

- Target file: `app/domains/notifications/bot_service.py`.
- Existing extracted notification bot services use `set_dependency_providers(...)` configured from `bot_service.py`; follow that pattern so tests can still monkeypatch legacy globals.
- Event consumers for `notify.library.new_episode` and `notify.library.new_item` are already subscribed in `NotificationBot`; this slice must keep those event names and payload shapes stable.
