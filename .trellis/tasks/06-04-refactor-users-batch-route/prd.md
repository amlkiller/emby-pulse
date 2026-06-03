# Refactor Users Batch Route

## Goal

Reduce `app/domains/users/router.py` mixed responsibilities by extracting the batch user management endpoint into a dedicated domain router module, preserving route behavior, route order, compatibility exports, and existing monkeypatch-oriented tests.

## Requirements

* Move `POST /api/manage/users/batch` and its dedicated request model out of `app/domains/users/router.py`.
* Keep the public handler name `api_manage_users_batch` and model name `BatchActionModelLocal` available from `app.domains.users.router`.
* Preserve existing responses, permission checks, media health check timing, audit log payloads, DAO/media calls, and exception mapping.
* Preserve dynamic monkeypatch compatibility for dependencies currently patched through `app.domains.users.router`, including `media_api`, `user_dao`, `is_admin_user`, `verify_emby_admin_password`, `clone_policy`, `safe_error_message`, `get_client_ip`, and `add_audit_log`.
* Keep FastAPI route order stable relative to neighboring users routes.
* Add or update focused regression coverage for the extraction boundary.

## Acceptance Criteria

* [ ] `app/domains/users/router.py` includes a child router for the batch route instead of defining the route inline.
* [ ] `app/domains/users/batch_router.py` owns `BatchActionModelLocal` and `api_manage_users_batch`.
* [ ] Existing imports from `app.domains.users.router` for the moved model and handler still work.
* [ ] Focused tests verify route inclusion/order, compatibility exports, and early-return behavior for login/admin/size/health checks.
* [ ] Changed Python files compile with `uv run python -m compileall`.
* [ ] Focused users tests pass with `uv run pytest tests/test_users_public_service_facade.py -v`.
* [ ] Full test suite passes with `uv run pytest tests/ -v`.

## Definition of Done

* Behavior-preserving code change committed separately from Trellis bookkeeping.
* Trellis task archived after successful verification.
* Session journal records the slice and verification outcome.

## Technical Approach

Follow the existing child-router pattern used by `new_user_router.py`, `delete_router.py`, and `single_user_router.py`: the child router owns the route and local dependency providers, while `users/router.py` wires providers with lambdas that dynamically resolve legacy globals for monkeypatch compatibility.

## Out of Scope

* Do not change batch operation semantics or response text.
* Do not move shared `clone_policy` or policy constants in this slice.
* Do not refactor `UserUpdateModelEx`, library route, update route, or users list route in this slice.
* Do not introduce new service-layer abstractions beyond the route extraction boundary.

## Technical Notes

* Architecture audit target: `docs/架构审计.md` P2 item 5, small behavior-preserving slices for large domain files.
* Relevant specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/error-handling.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/guides/code-reuse-thinking-guide.md`.
* Existing child routers to mirror: `app/domains/users/new_user_router.py`, `app/domains/users/delete_router.py`, `app/domains/users/single_user_router.py`.
