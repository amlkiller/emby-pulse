# plugins router public facade boundary

## Goal

Move the plugin admin router off private user auth and system view imports so it uses existing public facade boundaries for permission checks and template context assembly.

## What I already know

* `docs/架构审计.md` P2 calls out cross-domain direct imports and plugin/core boundary coupling as ongoing architecture debt.
* `app/domains/plugins/router.py` imports `app.domains.users.auth.is_admin_user`, `app.domains.users.auth.check_permission`, and function-local `app.domains.system.views.get_common_vars`.
* `app.domains.users.public_service` already exposes `is_admin_user(request)` and `check_permission(request, page)`.
* `app.domains.system.public_service` already exposes `get_common_vars(request, active_page, extra_vars=None)`.
* The points page boundary slice established the same facade pattern and tests.

## Assumptions

* This is a behavior-preserving refactor. Route URLs, response shapes, template name, redirects, admin checks, and plugin enable/config behavior should remain unchanged.
* Domain-internal modules may keep using their private helpers; this task only targets `app/domains/plugins/router.py` as an external cross-domain caller.

## Requirements

* Update `app/domains/plugins/router.py` to use `users.public_service` and `system.public_service`.
* Remove direct imports from `app.domains.users.auth` and `app.domains.system.views` in the plugins router.
* Add focused tests that guard the plugins router import boundary.
* Add a behavior test for the `/plugins` page path proving it calls public facades for permission and template context.
* Keep changes narrow; do not refactor plugin runtime behavior or unrelated routes.

## Acceptance Criteria

* [ ] `app/domains/plugins/router.py` has no import from `app.domains.users.auth`.
* [ ] `app/domains/plugins/router.py` has no import from `app.domains.system.views`.
* [ ] Tests fail if those private imports are reintroduced in the plugins router.
* [ ] Tests prove the plugins page uses public facade functions for permission and context.
* [ ] Focused tests, compile checks, import checks, and full `tests/` suite pass with the repository `uv run --with-requirements requirements.txt` command pattern.

## Definition of Done

* Code and tests are committed in one work commit.
* Completed task is archived through Trellis.
* Session journal records the work commit.

## Out of Scope

* Refactoring plugin runtime APIs.
* Migrating all remaining domain routers off `users.auth`.
* Changing permission semantics or template context contents.

## Technical Notes

* Relevant specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/backend/error-handling.md`.
* Relevant thinking guides: `.trellis/spec/guides/cross-layer-thinking-guide.md`, `.trellis/spec/guides/code-reuse-thinking-guide.md`.
* Source audit: `docs/架构审计.md` section "P2 问题 / 跨域直接 import 仍然较多".
