# Refactor Notification User Bot Lottery Draw

## Goal

Split the `do_lottery_draw()` implementation out of `app/domains/notifications/user_bot_service.py` into a domain-local named service module, reducing the remaining mixed responsibilities in the user bot compatibility module while preserving lottery draw behavior.

## Requirements

* Extract the body of `do_lottery_draw()` into a new `app/domains/notifications/*_service.py` module.
* Keep `user_bot_service.do_lottery_draw()` as a compatibility wrapper used by scheduler and admin manual draw callers.
* Preserve draw date handling, already-drawn/no-ticket skips, deleted-account filtering fallback, winner calculation, prize persistence, notification formatting, group allowlist parsing, direct Telegram send behavior, and error logging.
* Configure dependencies from `user_bot_service.py` through lazy providers so legacy globals and monkeypatches remain compatible.
* Do not change lottery command purchase/result behavior, scheduler timing, admin clear-draw behavior, or point DAO contracts.

## Acceptance Criteria

* [ ] `user_bot_service.py` delegates lottery draw handling to the extracted service.
* [ ] New focused boundary coverage verifies representative draw branches through legacy monkeypatches.
* [ ] Changed modules compile and import through `uv run`.
* [ ] Full `uv run pytest tests/ -v` passes before the work commit.

## Definition of Done

* Run focused compile/import checks for changed files.
* Run focused lottery draw tests.
* Run the full test suite.
* Commit code/test changes separately from Trellis archive and journal bookkeeping.
* Archive the Trellis task and record a session journal entry referencing the work commit.

## Technical Approach

Create `user_bot_lottery_draw_service.py` with `do_lottery_draw()` and `set_dependency_providers(...)`. The module will own the extracted draw workflow while depending on lazy providers for `datetime`, `random`, `point_dao`, `media_api`, `get_user_bot_allowed_groups`, `get_user_bot_lottery_cost`, `telegram_client`/send behavior, and logger access.

## Decision (ADR-lite)

Context: `user_bot_service.py` still contains compatibility wrappers, provider wiring, the `UserBot` lifecycle class, welcome handling, and a large lottery draw workflow.

Decision: Extract only lottery draw orchestration in this slice, leaving command wrappers and scheduler wiring intact.

Consequences: The user bot compatibility module shrinks further without changing public functions. The new service can later be used by admin manual draw callers directly once cross-module compatibility is cleaned up.

## Out of Scope

* Moving lottery purchase/result command implementations.
* Changing lottery prize rules, ticket schemas, or point DAO methods.
* Refactoring admin bot endpoints or game router lottery views.
* Moving `UserBot` class or group welcome handling.

## Technical Notes

* Architecture audit target: `docs/架构审计.md` P2 item 5, large mixed-responsibility domain files.
* Applicable specs: `.trellis/spec/backend/index.md`, `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/backend/logging-guidelines.md`, `.trellis/spec/guides/index.md`.
* Primary file inspected: `app/domains/notifications/user_bot_service.py`.
* Existing scheduler service already calls `do_lottery_draw` through a provider, so keeping the wrapper preserves timing behavior.
