# System Invitation Public Service Facade

## Goal

Reduce cross-domain coupling from the architecture audit by moving external invitation-code callers off the private `app.domains.system.invitation_dao` module and onto a narrow public system facade.

## Requirements

* Add `app/domains/system/public_service.py` as the public cross-domain boundary for invitation-code behavior.
* Preserve all current invitation DAO behavior and return shapes by delegating directly to existing DAO functions.
* Update external callers in `points` and `notifications` to use the public facade instead of importing `invitation_dao` directly.
* Keep system-domain internal callers, such as `system.views`, free to use the DAO directly while they are inside the same domain.
* Add focused tests proving the public facade delegates correctly and selected external callers no longer import `app.domains.system.invitation_dao`.

## Acceptance Criteria

* [ ] `points.router` renew-code flow uses `app.domains.system.public_service`.
* [ ] `notifications.user_bot_service` registration/renew invitation flows use `app.domains.system.public_service`.
* [ ] The public facade exposes only the invitation functions needed by external callers in this slice.
* [ ] Focused boundary tests pass.
* [ ] Changed Python files compile through `uv run --with-requirements requirements.txt`.
* [ ] Full pytest suite passes.

## Definition of Done

* Behavior remains route/API compatible.
* No new cross-domain private DAO imports are introduced.
* Work is committed as one coherent refactor commit, then the Trellis task is archived and journaled.

## Technical Approach

Create `app.domains.system.public_service` as a thin delegating module over `invitation_dao` functions currently used outside the system domain:

* `get_available_registration_invitation`
* `restore_invitation_code_usage`
* `claim_invitation_usage`
* `save_code_registration_meta_and_finish_invitation`
* `renew_user_with_invitation_code`

Then replace external imports in `app/domains/points/router.py` and `app/domains/notifications/user_bot_service.py` with the public facade. Add tests mirroring the existing public-service facade test style.

## Out of Scope

* Moving invitation DAO schema or persistence logic.
* Refactoring `system.views` invitation page/registration internals.
* Splitting large notification or points files.
* Changing invite-code validation, errors, messages, route responses, or database writes.

## Technical Notes

* Audit source: `docs/架构审计.md` P2 item 6 calls out cross-domain direct imports and recommends public service/facade boundaries.
* Existing facade pattern examples: `notifications.public_service`, `users.public_service`, `media_requests.public_service`, `reports.public_service`.
* Current external invitation DAO import sites: `app/domains/points/router.py`, `app/domains/notifications/user_bot_service.py`.
