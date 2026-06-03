# Refactor Users Audit Log Router

## Goal

Continue the architecture audit P2 large-domain-file cleanup by extracting the audit log management endpoints from `app/domains/users/router.py` into a domain-local child router, reducing mixed responsibilities while preserving existing behavior.

## Requirements

* Add a new users-domain module for the audit log routes.
* Move the existing audit log management endpoints out of `app/domains/users/router.py` without changing URLs, HTTP methods, payloads, auth checks, response shapes, DAO calls, or exception handling.
* Keep `app.domains.users.router` compatibility exports for moved endpoint functions where external imports/tests may reference them.
* Include the new child router from `app/domains/users/router.py` at the original route position relative to surrounding routes.
* Keep the slice narrow; do not refactor unrelated user management, invitation, library, or avatar routes.

## Acceptance Criteria

* [ ] `app/domains/users/router.py` no longer defines the audit log route bodies directly.
* [ ] The existing audit log routes remain registered through `app.domains.users.router.router`.
* [ ] Moved endpoint function names remain importable from `app.domains.users.router`.
* [ ] Focused route registration/import checks pass.
* [ ] Existing relevant users router tests pass.
* [ ] The full test suite passes before commit.

## Definition of Done

* Tests added or updated where useful to lock route inclusion/compatibility.
* Compile/import checks pass for changed modules.
* `git diff --check` passes.
* No spec update is needed unless the work discovers a new project convention or gotcha.
* Code changes are committed before task archive and journal bookkeeping.

## Technical Approach

Create `app/domains/users/audit_log_router.py` with its own `APIRouter`, move the adjacent audit log endpoints from `users/router.py`, import the moved functions plus child router back into `users/router.py`, and call `router.include_router(audit_log_router)` at the same location where the first moved route currently appears.

## Out of Scope

* Changing audit log persistence, pagination, statistics, delete, or clear semantics.
* Changing administrator authorization policy.
* Renaming routes or endpoint function names.
* Broad users-domain router decomposition beyond this one route group.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Candidate source file: `app/domains/users/router.py`, currently still one of the larger domain files after recent child-router extractions.
* Existing child-router pattern in the same domain: `list_router.py`, `request_permission_router.py`, `tag_router.py`, and `template_router.py`.
