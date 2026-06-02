# Playback Stats Public Auth Facade Boundary

## Goal

Move `app/domains/playback/stats.py` admin checks off the private users auth module and through the users public facade, preserving existing playback stats API behavior.

## Requirements

- Replace the private `app.domains.users.auth` import in `app/domains/playback/stats.py` with the users public facade.
- Route all existing `is_admin_user(request)` checks in the module through `app.domains.users.public_service`.
- Preserve endpoint paths, response payloads/messages, DAO/query calls, media API calls, cache behavior, and side-effect ordering.
- Add focused regression tests that prove:
  - `stats.py` no longer imports private users auth.
  - Representative non-admin routes deny before query/media side effects.
  - Representative admin routes call through the public facade and preserve success responses.

## Acceptance Criteria

- [ ] Changed stats module has no private `app.domains.users.auth` import.
- [ ] Existing unauthorized responses still return the same payloads.
- [ ] Admin success paths still call existing helpers in the same order.
- [ ] Focused boundary tests pass.
- [ ] Compile, import, diff hygiene, private-import scan, and full pytest suite pass before commit.

## Definition of Done

- Tests added for the import boundary and representative authorization behavior.
- Python verification commands use `uv run`.
- Work commit is created for code/test files, followed by separate Trellis archive and journal commits.

## Technical Approach

Import `app.domains.users.public_service` as `user_service`, replace the module-level auth helper and each existing `is_admin_user(request)` route guard with `user_service.is_admin_user(request)`, and avoid restructuring playback stats logic.

## Out of Scope

- No endpoint, schema, response, DAO/query, media, cache, or stats calculation behavior changes.
- No migration of users-domain-internal imports outside `app/domains/playback/stats.py`.
- No split of the large playback stats module in this task.

## Technical Notes

- Audit source: `docs/架构审计.md` P2 issue 6, cross-domain private import cleanup.
- Target file inspected: `app/domains/playback/stats.py`.
- Existing local test style:
  - `tests/test_playback_insight_public_auth_facade_boundary.py`
  - `tests/test_playback_dedupe_public_auth_facade_boundary.py`
  - `tests/test_playback_search_auth_import_boundary.py`
