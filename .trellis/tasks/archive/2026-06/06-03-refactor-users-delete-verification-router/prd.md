# Refactor Users Delete Verification Router

## Goal

Continue the architecture audit P2 large-domain-file cleanup by extracting the users delete-verification endpoints and helper logic from `app/domains/users/router.py` into a domain-local module, reducing mixed responsibilities while preserving route behavior.

## Requirements

* Add a new users-domain module for delete-verification/admin-password routes.
* Move the existing `GET /api/manage/user/admin_list`, `POST /api/manage/user/verify_password`, and `POST /api/manage/user/check_delete_verified` endpoints out of `app/domains/users/router.py`.
* Preserve route URLs, methods, session/admin checks, response shapes, Emby media API calls, logging, timeout values, verification expiry rules, and exception behavior.
* Keep `app.domains.users.router` compatibility exports for moved functions, `PasswordVerifyModel`, `verify_emby_admin_password`, `get_emby_admin_users`, and `APP_START_TIME`.
* Keep downstream delete/batch-delete code in `users/router.py` able to call `verify_emby_admin_password` and use its existing `APP_START_TIME` compatibility global.
* Include the new child router from `app/domains/users/router.py` at the original route position relative to audit log and later user-management routes.
* Keep the slice narrow; do not refactor user deletion, user creation/update, invitation, image, or library routes.

## Acceptance Criteria

* [ ] `app/domains/users/router.py` no longer defines the delete-verification route bodies directly.
* [ ] The three moved routes remain registered through `app.domains.users.router.router`.
* [ ] Moved endpoint/helper names remain importable from `app.domains.users.router`.
* [ ] The audit log routes still precede delete-verification routes and later user-management routes still follow them.
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

Create `app/domains/users/delete_verification_router.py` with its own `APIRouter`, move the delete-verification routes and password helper functions there, import the moved names back into `users/router.py`, and call `router.include_router(delete_verification_router)` where the first moved route currently appears. Keep the original module globals re-exported so existing callers and tests can still reference `app.domains.users.router.*`.

## Out of Scope

* Changing delete authorization or password verification policy.
* Changing session key names or verification duration.
* Changing user deletion or batch deletion flows beyond imports required for compatibility.
* Extracting unrelated user management routes.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Existing child-router pattern in `app/domains/users/`: `audit_log_router.py`, `list_router.py`, `request_permission_router.py`, `tag_router.py`, and `template_router.py`.
* `api_manage_user_delete` and `api_manage_users_batch` currently share `APP_START_TIME` / `verify_emby_admin_password`; preserve those names in `users/router.py`.
