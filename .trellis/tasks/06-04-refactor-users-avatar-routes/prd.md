# Refactor Users Avatar Routes

## Goal

Split avatar-related HTTP routes out of `app/domains/users/router.py` into a smaller users-domain child router, following `docs/架构审计.md` P2 item 5. Preserve all existing route URLs, response shapes, validation behavior, side effects, and compatibility exports.

## Requirements

* Extract these handlers from `users/router.py` into a domain-local users module:
  * `get_user_avatar`
  * `api_update_user_image`
  * `api_user_self_avatar`
* Keep the same route paths, HTTP methods, function signatures, and return behavior.
* Include the new child router from `users/router.py` at the same relative position so route ordering remains compatible.
* Re-export the extracted functions from `users/router.py` by importing them, matching existing users child-router compatibility patterns.
* Preserve admin/session checks, URL safety validation, image magic-byte validation, size limits, media API calls, audit logging, and safe error mapping.
* Preserve monkeypatch compatibility by wiring dependencies through providers that read legacy globals from `users/router.py` dynamically where needed.
* Add focused tests for child-router inclusion/compat exports and security short-circuit behavior.

## Acceptance Criteria

* [ ] `app/domains/users/router.py` is smaller and delegates avatar routes to a new users-domain child router.
* [ ] Existing public route paths and compatibility imports still work from `app.domains.users.router`.
* [ ] Focused tests cover avatar child route inclusion, compatibility exports, admin denial before side effects, and self-avatar login denial before file reads.
* [ ] Focused users tests pass.
* [ ] Full test suite passes.
* [ ] Git working tree is clean after code/test commit, task archive, and journal record.

## Definition of Done

* Tests added or updated for the extracted boundary.
* Project verification run through `uv run`.
* Code/test changes committed separately from Trellis archive and journal bookkeeping.
* No unrelated refactors or route behavior changes.

## Technical Approach

Create `app/domains/users/avatar_router.py` with `router = APIRouter()` and provider injection for `media_api`, `network_client`, `is_admin_user`, `check_magic_bytes`, `safe_error_message`, `get_client_ip`, and `add_audit_log`. Import and include this child router from `app/domains/users/router.py`, while keeping compatibility imports for the three extracted functions.

## Decision (ADR-lite)

Context: `users/router.py` is currently one of the largest domain files and already includes several child routers for audit logs, invitations, delete verification, library visibility, lists, permissions, tags, and templates.

Decision: Extract avatar routes as a child router because they form a coherent HTTP boundary with isolated media/image concerns.

Consequences: This reduces the main router and follows existing local structure. User creation/update/delete flows remain in place for later slices.

## Out of Scope

* Changing avatar upload/download semantics.
* Moving user creation, update, batch, delete, or pin routes.
* Changing media API client behavior or image validation internals.
* Adding new avatar features.

## Technical Notes

* Source requirement: `docs/架构审计.md` P2 item 5 recommends small behavior-preserving slices for large domain files.
* Existing pattern: `users/router.py` imports child routers and compatibility exports from `delete_verification_router.py`, `invitation_router.py`, `library_visibility_router.py`, and others.
* Avatar routes currently mix admin avatar fetch/update and C-end self avatar update in the main router.
