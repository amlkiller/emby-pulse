# risk router public auth facade boundary

## Goal

Move the risk router off the private users auth module for its admin checks, using the existing users public facade instead.

## What I already know

* `docs/架构审计.md` P2 calls out cross-domain direct imports as ongoing architecture debt and recommends public service/facade boundaries.
* `app/domains/risk/router.py` imports `app.domains.users.auth.is_admin_user`.
* The risk router has both return-payload admin failures and `HTTPException` admin failures.
* `app.domains.users.public_service.is_admin_user(request)` already exists and delegates to the private auth implementation.

## Assumptions

* This is a behavior-preserving refactor.
* Risk route URLs, response payloads, HTTP status codes, media-server calls, DAO/config calls, and risk service side effects should remain unchanged.
* This task only targets the risk router auth import boundary.

## Requirements

* Update `app/domains/risk/router.py` to use `app.domains.users.public_service`.
* Remove the direct `app.domains.users.auth` import from the risk router.
* Add focused tests that guard the import boundary.
* Add behavior tests proving representative risk routes use the public admin facade while preserving existing unauthorized/admin behavior.
* Keep changes narrow.

## Acceptance Criteria

* [ ] `app/domains/risk/router.py` has no import from `app.domains.users.auth`.
* [ ] Tests fail if that private import is reintroduced.
* [ ] Tests prove a return-payload route, such as `get_risk_config`, returns `{"error": "需要管理员权限"}` through the public facade when admin is denied.
* [ ] Tests prove `get_risk_config` returns existing config payload through the public facade when admin is allowed.
* [ ] Tests prove an exception-style route, such as `update_risk_config`, raises `403` through the public facade before writing config when admin is denied.
* [ ] Tests prove `update_risk_config` writes existing config values through the public facade when admin is allowed.
* [ ] Focused tests, compile checks, import checks, private import search, and full `tests/` suite pass with the repository `uv run --with-requirements requirements.txt` command pattern.

## Definition of Done

* Code and tests are committed in one work commit.
* Completed task is archived through Trellis.
* Session journal records the work commit.

## Out of Scope

* Refactoring risk service or DAO internals.
* Changing media-server calls.
* Migrating notification calls in `risk_service.py`.
* Migrating other routers off `users.auth`.
* Changing risk route URLs or response shapes.

## Technical Notes

* Relevant specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/backend/error-handling.md`.
* Relevant thinking guide: `.trellis/spec/guides/cross-layer-thinking-guide.md`.
* Source audit: `docs/架构审计.md` section "P2 问题 / 跨域直接 import 仍然较多".
