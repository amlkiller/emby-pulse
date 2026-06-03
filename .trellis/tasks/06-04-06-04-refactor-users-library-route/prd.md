# Refactor Users Library Route

## Goal

Reduce `app/domains/users/router.py` mixed responsibilities by extracting the admin user library permission save endpoint into a dedicated users domain router module, preserving route behavior, route order, compatibility exports, and existing monkeypatch-oriented tests.

## Requirements

* Move `POST /api/manage/user/library` out of `app/domains/users/router.py`.
* Keep `api_manage_user_library` available from `app.domains.users.router` for compatibility.
* Reuse the existing `UserUpdateModelEx` model exported by `app.domains.users.update_router`; do not move or duplicate the model in this slice.
* Preserve existing responses, permission checks, media health check timing, cache invalidation, user lookup, policy mutation, DAO synchronization, media writes, and exception mapping.
* Preserve dynamic monkeypatch compatibility for dependencies currently patched through `app.domains.users.router`, including `media_api`, `user_dao`, `user_service`, `is_admin_user`, and `safe_error_message`.
* Keep FastAPI route order stable relative to neighboring users routes, especially before the update, new-user, and dynamic user-id routes.
* Add or update focused regression coverage for the extraction boundary.

## Acceptance Criteria

* [ ] `app/domains/users/router.py` includes a child router for the library-save route instead of defining it inline.
* [ ] `app/domains/users/library_update_router.py` owns `api_manage_user_library`.
* [ ] Existing imports from `app.domains.users.router` for the moved handler still work.
* [ ] Focused tests verify route inclusion/order, compatibility exports, authorization/health early returns, and representative success/error mapping through legacy providers.
* [ ] Changed Python files compile with `uv run python -m compileall`.
* [ ] Focused users tests pass with `uv run pytest tests/test_users_public_service_facade.py -v`.
* [ ] Full test suite passes with `uv run pytest tests/ -v`.

## Definition of Done

* Behavior-preserving code change committed separately from Trellis bookkeeping.
* Trellis task archived after successful verification.
* Session journal records the slice and verification outcome.

## Technical Approach

Follow the existing child-router provider pattern: the child router owns the route and provider defaults, while `users/router.py` wires providers with lambdas that dynamically resolve legacy globals for monkeypatch compatibility.

## Out of Scope

* Do not change user library save response fields or Emby policy mutation semantics.
* Do not move `UserUpdateModelEx`; it already belongs to `update_router.py`.
* Do not move shared policy constants or `clone_policy` out of `users/router.py` in this slice.
* Do not introduce new service-layer abstractions beyond the route extraction boundary.

## Technical Notes

* Architecture audit target: `docs/架构审计.md` P2 item 5, small behavior-preserving slices for large domain files.
* Relevant specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/error-handling.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/guides/code-reuse-thinking-guide.md`.
* Existing child routers to mirror: `app/domains/users/update_router.py`, `app/domains/users/new_user_router.py`, `app/domains/users/batch_router.py`, `app/domains/users/manage_list_router.py`.
