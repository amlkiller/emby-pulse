# Refactor Users Update Route

## Goal

Reduce `app/domains/users/router.py` mixed responsibilities by extracting the admin user update endpoint into a dedicated users domain router module, preserving route behavior, route order, compatibility exports, and existing monkeypatch-oriented tests.

## Requirements

* Move `POST /api/manage/user/update` out of `app/domains/users/router.py`.
* Move `UserUpdateModelEx` to the new child router module because the update route owns most of the model fields.
* Keep `UserUpdateModelEx` and `api_manage_user_update` available from `app.domains.users.router` for compatibility.
* Keep `POST /api/manage/user/library` in `app/domains/users/router.py` for this slice, using the compatibility-exported `UserUpdateModelEx`.
* Preserve existing responses, permission checks, media health check timing, cache invalidation, DAO/media writes, template policy cloning, audit log payloads, and exception mapping.
* Preserve dynamic monkeypatch compatibility for dependencies currently patched through `app.domains.users.router`, including `media_api`, `user_dao`, `user_service`, `is_admin_user`, `clone_policy`, `safe_error_message`, `get_client_ip`, `add_audit_log`, and `datetime`.
* Keep FastAPI route order stable relative to neighboring users routes.
* Add or update focused regression coverage for the extraction boundary.

## Acceptance Criteria

* [ ] `app/domains/users/router.py` includes a child router for the update route instead of defining it inline.
* [ ] `app/domains/users/update_router.py` owns `UserUpdateModelEx` and `api_manage_user_update`.
* [ ] Existing imports from `app.domains.users.router` for the moved model and handler still work.
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

* Do not change user update response fields, audit detail text, or Emby policy mutation semantics.
* Do not extract `POST /api/manage/user/library` in this slice.
* Do not move shared policy constants or `clone_policy` out of `users/router.py` in this slice.
* Do not introduce new service-layer abstractions beyond the route extraction boundary.

## Technical Notes

* Architecture audit target: `docs/架构审计.md` P2 item 5, small behavior-preserving slices for large domain files.
* Relevant specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/error-handling.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/guides/code-reuse-thinking-guide.md`.
* Existing child routers to mirror: `app/domains/users/new_user_router.py`, `app/domains/users/batch_router.py`, `app/domains/users/manage_list_router.py`.
