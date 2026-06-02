# Media Requests Public Service Facade

## Goal

Continue the architecture audit P2 cross-domain boundary work by introducing a narrow public media requests facade and moving selected notification-domain callers away from direct imports of `app.domains.media_requests.media_request_dao`, `app.domains.media_requests.gap_dao`, and `app.domains.media_requests.gaps` internals.

## Requirements

- Add a public media requests facade module such as `app/domains/media_requests/public_service.py`.
- Expose the current media request and gap operations needed by notification-domain callers:
  - request submission and recent-request listing for the user bot
  - request approval/status/sync helpers for the admin bot
  - TG binding lookup used for request-status notifications
  - gap deletion/cache updates used when library episodes arrive
- Preserve existing behavior, return values, exception behavior, and call arguments by delegating to the existing DAO/gap implementation.
- Migrate selected callers outside `app/domains/media_requests/` from direct `media_request_dao`, `gap_dao`, and `gaps.scan_state/state_lock` imports to the facade.
- Keep media-requests-domain-internal direct DAO/gap usage out of scope.
- Keep schema/DAO tests that intentionally test `media_request_dao` or `gap_dao` out of scope.
- Add focused regression tests that prove the facade delegates correctly and selected notification callers no longer import media request private DAO/gap internals directly.
- Do one consolidated verification pass and one work commit for this task.

## Acceptance Criteria

- `app/domains/media_requests/public_service.py` exists and exposes narrow functions for:
  - `submit_single_media_request(...)`
  - `list_user_recent_requests(...)`
  - `finish_media_requests_for_item(...)`
  - `list_tg_bindings(...)`
  - `list_pending_sync_requests()`
  - `mark_sync_request_finished(...)`
  - `update_feedback_status(...)`
  - `get_request_summary_by_tmdb(...)`
  - `list_pending_requests_by_tmdb(...)`
  - `update_media_request_status(...)`
  - `delete_gap_record_by_series_episode(...)`
  - `delete_cleared_gap_record(...)`
  - `remove_gap_from_scan_state(...)`
- Selected notification modules no longer directly import:
  - `app.domains.media_requests.media_request_dao`
  - `app.domains.media_requests.gap_dao`
  - `app.domains.media_requests.gaps.state_lock`
  - `app.domains.media_requests.gaps.scan_state`
- Call-site arguments and behavior are unchanged for migrated callers.
- Facade delegation tests cover representative return-value and argument forwarding.
- A regression test covers `remove_gap_from_scan_state(...)` updating scan-state results and saving the gap cache.
- Boundary tests fail if selected notification callers reintroduce private media request DAO/gap imports.
- Compile, focused tests, ruff `E9,F63,F7,F82`, `git diff --check`, and full pytest pass in one consolidated verification pass.

## Out of Scope

- Do not split `app/domains/media_requests/router.py`, `gaps.py`, or DAO modules.
- Do not change media request schema, status values, notification messages, approval behavior, MoviePilot calls, or gap scan semantics.
- Do not migrate `app/domains/system/system_tools.py` community-cache access in this slice.
- Do not migrate tests that intentionally validate DAO/schema internals.
- Do not introduce typed request DTOs or a broader media request service.

## Technical Approach

- Create `app/domains/media_requests/public_service.py` as a thin facade over existing media request DAO and gap DAO functions.
- Implement `remove_gap_from_scan_state(series_id, season, episode)` inside the facade to encapsulate the existing cross-domain mutation of `gaps.scan_state` and `state_lock`.
- Replace selected imports/usages in:
  - `app/domains/notifications/bot_service.py`
  - `app/domains/notifications/user_bot_service.py`
- Add focused AST/source boundary tests for selected private media request imports in notification callers.
- Add unit tests that monkeypatch facade dependencies and assert arguments/return values are forwarded.

## Technical Notes

- Audit reference: `docs/架构审计.md` P2 issue 6, cross-domain direct imports.
- Existing architecture spec: `.trellis/spec/backend/directory-structure.md` says cross-domain behavior should prefer a public service function, narrow facade, or event boundary.
- This is a first media requests facade slice focused on notifications callers so it can be verified and committed as one coherent task.
