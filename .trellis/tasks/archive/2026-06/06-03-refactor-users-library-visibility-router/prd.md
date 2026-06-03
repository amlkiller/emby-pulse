# Refactor Users Library Visibility Router

## Goal

Continue the architecture audit P2 large-domain-file cleanup by extracting the C-side user library visibility endpoints from `app/domains/users/router.py` into a users-domain child router while preserving existing behavior.

## Requirements

* Add a new users-domain module for C-side library visibility routes.
* Move these endpoints out of `app/domains/users/router.py`:
  * `GET /api/user/libraries`
  * `POST /api/user/hidden_libraries`
* Preserve route URLs, methods, request model, session checks, response shapes, media API calls, user DAO calls, hidden-library filtering, admin-enabled-folder sync behavior, and exception handling.
* Keep `app.domains.users.router` compatibility exports for moved endpoint functions and `HiddenLibrariesModel`.
* Include the new child router from `app/domains/users/router.py` at the original route position between self password/avatar routes and invitation routes.
* Keep the slice narrow; do not refactor admin library routes, user management, invitation, avatar, or password routes.

## Acceptance Criteria

* [ ] `app/domains/users/router.py` no longer defines the C-side library visibility route bodies directly.
* [ ] The two moved routes remain registered through `app.domains.users.router.router`.
* [ ] Moved functions and request model remain importable from `app.domains.users.router`.
* [ ] Focused compile/import/route checks pass.
* [ ] Relevant users router tests pass.
* [ ] The full test suite passes before commit.

## Definition of Done

* Tests added or updated where useful to lock route inclusion and compatibility exports.
* Compile/import checks pass for changed modules.
* `git diff --check` passes.
* No spec update is needed unless the work discovers a new project convention or gotcha.
* Code changes are committed before task archive and journal bookkeeping.

## Technical Approach

Create `app/domains/users/library_visibility_router.py` with its own `APIRouter`, move `HiddenLibrariesModel`, `api_get_user_libraries`, and `api_update_hidden_libraries` there, then import the moved names and child router back into `users/router.py`. Use dependency providers for `media_api`, `user_dao`, and logging so the extracted module can preserve behavior while the old module keeps compatibility exports.

## Out of Scope

* Changing media library permission semantics.
* Changing Emby policy update behavior.
* Changing admin library or user-management endpoints.
* Broad users-domain router decomposition beyond this route group.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Existing users child-router pattern: `audit_log_router.py`, `delete_verification_router.py`, `invitation_router.py`, `list_router.py`, `request_permission_router.py`, `tag_router.py`, and `template_router.py`.
