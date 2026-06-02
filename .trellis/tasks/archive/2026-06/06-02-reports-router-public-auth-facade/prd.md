# reports router public auth facade boundary

## Goal

Move the reports router off the private users auth module for its admin checks, using the existing users public facade instead.

## What I already know

* `docs/架构审计.md` P2 calls out cross-domain direct imports as ongoing architecture debt and recommends public service/facade boundaries.
* `app/domains/reports/router.py` imports `app.domains.users.auth.is_admin_user`.
* The reports router already uses `app.domains.notifications.public_service` for notification push behavior.
* `app.domains.users.public_service.is_admin_user(request)` already exists and delegates to the private auth implementation.

## Assumptions

* This is a behavior-preserving refactor.
* Report preview and report push response shapes, Pillow handling, report generation, and notification push behavior should remain unchanged.
* This task only targets the reports router auth import boundary.

## Requirements

* Update `app/domains/reports/router.py` to use `app.domains.users.public_service`.
* Remove the direct `app.domains.users.auth` import from the reports router.
* Add focused tests that guard the import boundary.
* Add behavior tests proving report preview and report push use the public admin facade while preserving existing unauthorized/admin response behavior.
* Keep changes narrow.

## Acceptance Criteria

* [ ] `app/domains/reports/router.py` has no import from `app.domains.users.auth`.
* [ ] Tests fail if that private import is reintroduced.
* [ ] Tests prove report preview returns `403` when the public admin facade denies access.
* [ ] Tests prove report preview returns JPEG content when the public admin facade allows access and Pillow/report generation are available.
* [ ] Tests prove report push rejects non-admin callers with the existing error payload through the public admin facade.
* [ ] Focused tests, compile checks, import checks, private import search, and full `tests/` suite pass with the repository `uv run --with-requirements requirements.txt` command pattern.

## Definition of Done

* Code and tests are committed in one work commit.
* Completed task is archived through Trellis.
* Session journal records the work commit.

## Out of Scope

* Refactoring report generation internals.
* Changing notification public service behavior.
* Migrating other routers off `users.auth`.
* Changing report route URLs or response shapes.

## Technical Notes

* Relevant specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/backend/error-handling.md`.
* Relevant thinking guide: `.trellis/spec/guides/cross-layer-thinking-guide.md`.
* Source audit: `docs/架构审计.md` section "P2 问题 / 跨域直接 import 仍然较多".
