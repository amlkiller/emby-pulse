# Refactor playback stats item detail router

## Goal

Split `GET /api/stats/item_detail` out of `app/domains/playback/stats.py` into a playback domain child router while preserving the existing API contract and compatibility exports.

## Requirements

* Move only the item detail endpoint into `app/domains/playback/item_detail_router.py`.
* Keep route path, method, request parameters, response shape, login behavior, non-admin user scoping, media lookup fallback behavior, logging, and safe error handling unchanged.
* Keep `app.domains.playback.stats.api_item_detail` available as a compatibility export.
* Configure dependencies from `stats.py` through provider lambdas so monkeypatches to legacy `stats.*` globals are observed at request time.
* Preserve route order: after `/api/system/monitor`.
* Add focused tests covering route inclusion, compatibility export, unauthenticated short-circuit, successful admin lookup, non-admin scoped lookup, no-record response, and safe error fallback.

## Acceptance Criteria

* [ ] `stats.py` no longer defines `api_item_detail` inline.
* [ ] `item_detail_router.py` owns the endpoint and exposes `set_dependency_providers`.
* [ ] Existing and new playback stats facade tests pass.
* [ ] Full test suite passes.
* [ ] Code/test changes are committed separately from Trellis archive and journal bookkeeping.

## Definition of Done

* Compile changed Python files with `uv run python -m compileall`.
* Run focused tests for `tests/test_playback_stats_public_auth_facade_boundary.py`.
* Run `uv run pytest tests/ -v`.
* Run `git diff --check`.
* Commit the code/test slice.
* Archive the Trellis task and record the session journal.

## Technical Approach

Follow the existing playback stats child-router/provider pattern. The new router should hold the moved endpoint body and default to current dependencies, while `stats.py` wires provider lambdas that resolve legacy globals at request time.

## Out of Scope

* Rewriting the item detail query strategy.
* Extracting a service layer for item detail internals.
* Changing response fields, error messages, logging text, or permission policy.
* Broad cleanup outside this endpoint slice.

## Technical Notes

* Architecture audit target: `docs/架构审计.md` P2 item 5, domain files still too large and mixed-responsibility.
* Applicable specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/backend/error-handling.md`, `.trellis/spec/guides/code-reuse-thinking-guide.md`.
