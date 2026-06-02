# Users Public Service Facade

## Goal

Continue the architecture audit P2 cross-domain boundary work by introducing a narrow public users service facade and moving selected external domains/plugins away from direct imports of `app.domains.users.user_dao`, `app.domains.users.user_bot_dao`, and `app.domains.users.router.invalidate_emby_users_cache`.

## Requirements

- Add a public users facade module such as `app/domains/users/public_service.py`.
- Expose the current user operations needed by the selected external callers:
  - user display and expiry metadata used by plugins
  - user-bot binding lookups used by plugins
  - user metadata backup access used by the user backup plugin DAO
  - Emby users cache invalidation used by external domains
- Preserve existing behavior, return values, exception behavior, and call arguments by delegating to the existing DAO/router-owned implementation.
- Migrate external callers outside `app/domains/users/` from the selected direct imports to the facade.
- Keep `app.domains.users.auth` imports out of scope for this slice; route permission checks remain unchanged.
- Keep users-domain-internal direct DAO/router usage out of scope unless required for the facade.
- Add focused regression tests that prove the facade delegates correctly and selected external callers no longer import users private DAO/cache helpers directly.
- Do one consolidated verification pass and one work commit for this task.

## Acceptance Criteria

- `app/domains/users/public_service.py` exists and exposes narrow functions for:
  - `delete_user_meta_many(...)`
  - `get_user_display_name(...)`
  - `list_user_ids_with_expire_date(...)`
  - `list_users_with_expire_date(...)`
  - `list_permanent_user_expire_records(...)`
  - `get_tg_user_id_by_emby_id(...)`
  - `get_binding_by_emby_id(...)`
  - `get_user_meta(...)`
  - `list_all_user_meta(...)`
  - `upsert_user_meta_fields(...)`
  - `invalidate_emby_users_cache()`
- Selected external modules no longer directly import:
  - `app.domains.users.user_dao`
  - `app.domains.users.user_bot_dao`
  - `app.domains.users.router.invalidate_emby_users_cache`
- Call-site arguments and behavior are unchanged for migrated callers.
- Facade delegation tests cover representative return-value and argument forwarding.
- Boundary tests fail if selected external callers reintroduce the private users DAO/cache imports.
- Compile, focused tests, ruff `E9,F63,F7,F82`, `git diff --check`, and full pytest pass in one consolidated verification pass.

## Out of Scope

- Do not migrate `app.domains.users.auth` permission helper imports in this slice.
- Do not split `app/domains/users/router.py`.
- Do not change user DAO schemas, cache storage, cache semantics, auth behavior, or plugin business logic.
- Do not migrate users-domain-internal direct DAO usage.
- Do not introduce typed user DTOs or a broader user-management service.

## Technical Approach

- Create `app/domains/users/public_service.py` as a thin facade over existing users DAO/user-bot DAO functions.
- Move the Emby user cache invalidation implementation from `users.router` into the facade, then have `users.router` call/re-export the facade function for compatibility.
- Replace selected external imports in:
  - `app/plugins/auto_expire/plugin.py`
  - `app/plugins/keep_alive/plugin.py`
  - `app/plugins/user_backup/user_backup_dao.py`
  - `app/domains/media_requests/router.py`
  - `app/domains/notifications/user_bot_service.py`
  - `app/domains/system/views.py`
- Add focused AST/source boundary tests for selected private users DAO/cache imports.
- Add unit tests that monkeypatch facade dependencies and assert arguments/return values are forwarded.

## Technical Notes

- Audit reference: `docs/架构审计.md` P2 issue 6, cross-domain direct imports.
- Existing architecture spec: `.trellis/spec/backend/directory-structure.md` says cross-domain behavior should prefer a public service function, narrow facade, or event boundary.
- This task deliberately handles only a first users facade slice so it can be verified and committed as one coherent unit.
