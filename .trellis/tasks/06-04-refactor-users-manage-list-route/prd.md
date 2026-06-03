# Refactor Users Manage List Route

## Goal

Reduce `app/domains/users/router.py` mixed responsibilities by extracting the admin user list endpoint into a dedicated users domain router module, preserving route behavior, route order, compatibility exports, and existing monkeypatch-oriented tests.

## Requirements

* Move `GET /api/manage/users` out of `app/domains/users/router.py`.
* Move the directly-owned `check_expired_users()` helper with the route, because the helper is used only by that admin list endpoint.
* Keep `api_manage_users` and `check_expired_users` available from `app.domains.users.router` for compatibility.
* Preserve existing responses, permission checks, refresh cache behavior, media public host normalization, user meta mapping, Telegram binding mapping, pinned remark handling, and exception mapping.
* Preserve dynamic monkeypatch compatibility for dependencies currently patched through `app.domains.users.router`, including `media_api`, `user_dao`, `user_bot_dao`, `user_service`, `is_admin_user`, `get_media_server_public_host`, `safe_error_message`, and `datetime`.
* Keep FastAPI route order stable relative to neighboring users routes.
* Add or update focused regression coverage for the extraction boundary.

## Acceptance Criteria

* [ ] `app/domains/users/router.py` includes a child router for the admin user list route instead of defining the route inline.
* [ ] `app/domains/users/manage_list_router.py` owns `api_manage_users` and `check_expired_users`.
* [ ] Existing imports from `app.domains.users.router` for the moved handler/helper still work.
* [ ] Focused tests verify route inclusion/order, compatibility exports, early auth return, refresh cache behavior, response mapping, and error mapping through legacy providers.
* [ ] Changed Python files compile with `uv run python -m compileall`.
* [ ] Focused users tests pass with `uv run pytest tests/test_users_public_service_facade.py -v`.
* [ ] Full test suite passes with `uv run pytest tests/ -v`.

## Definition of Done

* Behavior-preserving code change committed separately from Trellis bookkeeping.
* Trellis task archived after successful verification.
* Session journal records the slice and verification outcome.

## Technical Approach

Follow the existing child-router pattern used by users route extractions: the child router owns the route and provider defaults, while `users/router.py` wires providers with lambdas that dynamically resolve legacy globals for monkeypatch compatibility.

## Out of Scope

* Do not change user list response fields or field names.
* Do not change expiration disable policy semantics.
* Do not refactor `UserUpdateModelEx`, library route, update route, or remaining policy constants in this slice.
* Do not introduce new service-layer abstractions beyond the route extraction boundary.

## Technical Notes

* Architecture audit target: `docs/架构审计.md` P2 item 5, small behavior-preserving slices for large domain files.
* Relevant specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/error-handling.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/guides/code-reuse-thinking-guide.md`.
* Existing child routers to mirror: `app/domains/users/libraries_router.py`, `app/domains/users/single_user_router.py`, `app/domains/users/batch_router.py`.
