# Remove Users Router Cache Wrappers

## Goal

Remove the `users.router` middle wrapper functions for the Emby users cache and point router-local callers at the real cache owner, `app.domains.users.public_service`.

## Requirements

- Delete `get_emby_users_cached()` from `app/domains/users/router.py` when it only forwards to `user_service.get_emby_users_cached()`.
- Delete `invalidate_emby_users_cache()` from `app/domains/users/router.py` when it only forwards to `user_service.invalidate_emby_users_cache()`.
- Replace all in-module calls in `users.router` with direct `user_service.get_emby_users_cached()` / `user_service.invalidate_emby_users_cache()`.
- Do not add any new wrapper, facade, alias, or compatibility function.
- Preserve user management behavior, response payloads, cache invalidation timing, and permission checks.
- Update tests so they assert the router no longer defines these pure forwarding wrappers and the endpoints still use the public service cache owner.

## Acceptance Criteria

- [x] `app/domains/users/router.py` no longer defines `get_emby_users_cached`.
- [x] `app/domains/users/router.py` no longer defines `invalidate_emby_users_cache`.
- [x] All former router-local cache calls now call `user_service` directly.
- [x] Tests cover the no-wrapper boundary and existing user management cache behavior.
- [x] Compile/import checks, wrapper-removal scan, focused tests, and full pytest suite pass.

## Definition of Done

- Work commit contains only code/test changes for this slice.
- Trellis task archive commit is separate.
- Journal records the work commit.

## Technical Notes

- Audit source: `docs/架构审计.md` P2 issue 5/6, reducing mixed responsibilities and unnecessary boundary indirection.
- Project rule: public service functions are semantic boundaries, not re-export bins; pure forwarding wrappers should be removed.
- The real cache owner remains `app.domains.users.public_service`, which owns the cache state and invalidation behavior.

## Out of Scope

- Moving the Emby users cache implementation.
- Changing user list cache TTL or invalidation semantics.
- Broader `users.router` decomposition.
