# playback calendar public facade boundary

## Goal

Move the playback calendar router off private user auth and system view imports so it uses existing public facade boundaries for permission checks, admin checks, and template context assembly.

## What I already know

* `docs/架构审计.md` P2 calls out cross-domain direct imports as ongoing architecture debt and recommends public service/facade boundaries.
* `app/domains/playback/calendar.py` imports `app.domains.users.auth.is_admin_user`, `app.domains.users.auth.check_permission`, and function-local `app.domains.system.views.get_common_vars`.
* `app.domains.users.public_service` already exposes `is_admin_user(request)` and `check_permission(request, page)`.
* `app.domains.system.public_service` already exposes `get_common_vars(request, active_page, extra_vars=None)`.
* Recent points/plugins boundary slices established the router facade pattern and AST tests.

## Assumptions

* This is a behavior-preserving refactor. Route URLs, response shapes, template name, redirects, calendar config update behavior, and permission semantics should remain unchanged.
* Domain-internal modules may keep using their own private helpers; this task only targets `app/domains/playback/calendar.py` as a cross-domain caller.

## Requirements

* Update `app/domains/playback/calendar.py` to use `users.public_service` and `system.public_service`.
* Remove direct imports from `app.domains.users.auth` and `app.domains.system.views` in the calendar router.
* Add focused tests that guard the calendar router import boundary.
* Add behavior tests for the `/calendar` page path proving it calls public facades and preserves login/permission redirects.
* Add a behavior test for `/api/calendar/config` proving it uses the public admin facade before updating TTL.
* Keep changes narrow; do not refactor calendar service behavior or unrelated playback modules.

## Acceptance Criteria

* [ ] `app/domains/playback/calendar.py` has no import from `app.domains.users.auth`.
* [ ] `app/domains/playback/calendar.py` has no import from `app.domains.system.views`.
* [ ] Tests fail if those private imports are reintroduced in the calendar router.
* [ ] Tests prove the calendar page uses public facade functions for permission and context.
* [ ] Tests prove the calendar config API uses the public admin facade.
* [ ] Focused tests, compile checks, import checks, and full `tests/` suite pass with the repository `uv run --with-requirements requirements.txt` command pattern.

## Definition of Done

* Code and tests are committed in one work commit.
* Completed task is archived through Trellis.
* Session journal records the work commit.

## Out of Scope

* Refactoring `calendar_service`.
* Migrating other playback routers off `users.auth`.
* Changing calendar cache semantics, public URL behavior, or template context contents.

## Technical Notes

* Relevant specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/backend/error-handling.md`.
* Relevant thinking guides: `.trellis/spec/guides/cross-layer-thinking-guide.md`, `.trellis/spec/guides/code-reuse-thinking-guide.md`.
* Source audit: `docs/架构审计.md` section "P2 问题 / 跨域直接 import 仍然较多".
