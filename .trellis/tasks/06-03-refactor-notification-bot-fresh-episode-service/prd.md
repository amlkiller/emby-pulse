# Refactor Notification Bot Fresh Episode Service

## Goal

Continue P2 item 5 from `docs/架构审计.md` by splitting another narrow responsibility out of `app/domains/notifications/bot_service.py`. This slice extracts fresh episode lookup and Emby timestamp parsing into a domain-local service while preserving the existing `SystemDaemon` wrapper behavior.

## Requirements

- Move `_check_fresh_episodes` behavior out of `bot_service.py` into a new notifications-local service module.
- Preserve existing behavior for missing admin id, non-200 Emby responses, empty item lists, unparsable timestamps, two-minute grouping, and swallowed dependency errors.
- Keep legacy `SystemDaemon._check_fresh_episodes` and `_parse_emby_time` wrappers so existing internal callers and monkeypatch-based tests remain compatible.
- Configure service dependencies from `bot_service.py` with dynamic providers for legacy globals such as `get_admin_id` and `media_api`.
- Add focused boundary tests for the extracted service behavior.

## Acceptance Criteria

- [ ] `bot_service.py` delegates fresh episode lookup and timestamp parsing to the new service.
- [ ] New boundary tests cover normal grouping and current edge cases.
- [ ] Focused tests pass.
- [ ] Import check passes for `bot_service.py` and the new service module.
- [ ] Full test suite passes.
- [ ] Code/test changes are committed separately from task archive and journal commits.

## Definition of Done

- Behavior-preserving refactor only; no product behavior changes.
- No broad extraction of the whole library notify loop in this slice.
- Trellis task is archived after the code/test commit.
- Session journal records the work commit.

## Out of Scope

- Extracting `_process_library_group`, `_push_episode_group`, or `_push_single_item`.
- Changing notification message formats, event names, or request auto-finish behavior.
- Introducing new cross-domain facades beyond the dependency providers needed for this slice.

## Technical Notes

- Target file: `app/domains/notifications/bot_service.py`.
- New module pattern should match existing extracted notification bot services, especially provider configuration from `bot_service.py` for monkeypatch compatibility.
- The relevant legacy methods currently live around the library notification group-processing block.
