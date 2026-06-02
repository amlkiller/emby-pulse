# points page public facade boundary

## Goal

Move the points page/router off private cross-domain imports so it uses public facade boundaries for user permission checks and system template context assembly.

## What I already know

* `docs/架构审计.md` P2 calls out cross-domain direct imports as ongoing architecture debt and recommends narrow public service/facade boundaries.
* `app/domains/points/router.py` imports `app.domains.users.auth.is_admin_user`, `app.domains.users.auth.check_permission`, and `app.domains.system.views.get_common_vars` directly.
* `app/domains/users/public_service.py` already exposes `is_admin_user(request)`.
* `app/domains/system/public_service.py` exists for cross-domain callers but does not yet expose template common-vars assembly.
* Prior audit slices added AST boundary tests for public facades and import restrictions.

## Assumptions

* This is a behavior-preserving refactor. Route URLs, response shapes, template names, redirect status codes, and permission semantics should remain unchanged.
* Domain-internal callers may keep using their own private modules; this task targets `points` as an external caller of `users` and `system` internals.

## Requirements

* Add any missing public facade functions needed by `app/domains/points/router.py`.
* Update `app/domains/points/router.py` to call users/system public facades instead of importing private `users.auth` or `system.views`.
* Add focused tests that protect the facade delegation and the points router import boundary.
* Keep changes narrow; do not split the points router or alter unrelated system/users modules.

## Acceptance Criteria

* [ ] `app/domains/points/router.py` has no import from `app.domains.users.auth`.
* [ ] `app/domains/points/router.py` has no import from `app.domains.system.views`.
* [ ] Public facade tests cover any newly exposed delegation function.
* [ ] A boundary test fails if the points router reintroduces private users/system imports.
* [ ] Focused tests, compile checks, and full `tests/` suite pass with the repository `uv run --with-requirements requirements.txt` command pattern.

## Definition of Done

* Code and tests are committed in one work commit.
* Completed task is archived through Trellis.
* Session journal records the work commit.

## Out of Scope

* Refactoring other system modules that import `users.auth`.
* Splitting `app/domains/points/router.py` by responsibility.
* Changing permission behavior or template context contents.

## Technical Notes

* Relevant specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/backend/error-handling.md`.
* Relevant thinking guides: `.trellis/spec/guides/cross-layer-thinking-guide.md`, `.trellis/spec/guides/code-reuse-thinking-guide.md`.
* Source audit: `docs/架构审计.md` section "P2 问题 / 跨域直接 import 仍然较多".
