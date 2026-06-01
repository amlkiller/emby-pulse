# Remove Infra/Core Domain Reverse Dependencies

## Goal

Address P1 item 2 from `docs/架构审计.md`: remove foundation-layer imports from `app/infra` and `app/core` into concrete domain modules.

## Requirements

- Remove `app.infra.db.database -> app.domains.playback.queries` dependency.
- Remove `app.core.jwt_token -> app.domains.system.api_token_dao` dependency.
- Preserve compatibility for existing imports and call sites:
  - `app.infra.db.database.get_base_filter(...)`
  - `app.domains.playback.queries.get_base_filter(...)`
  - `app.domains.system.api_token_dao.*`
  - `app.core.jwt_token.verify_api_token(...)`
- Keep behavior unchanged:
  - playback base filter still applies explicit user filter and hidden-user filtering.
  - API token verification still hashes the token, confirms DB presence, respects DB expiry, and degrades to JWT-only validation on DB errors.
- Add focused regression coverage proving `app.infra.db.database` and `app.core.jwt_token` do not import the concrete domain modules called out by the audit.
- Keep unrelated lifecycle, schema ownership, and large-domain splitting out of scope.

## Acceptance Criteria

- [x] No `app/infra/**` Python file imports from `app.domains.*`.
- [x] No `app/core/**` Python file imports from `app.domains.*`.
- [x] `get_base_filter(...)` behavior is preserved through existing compatibility import points.
- [x] API token DAO compatibility functions still expose the same signatures used by `app.domains.system.api_tokens`.
- [x] Regression tests cover the removed reverse dependencies.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

- Create an infra-owned playback filter helper for the generic `PlaybackActivity` user filter logic.
- Change `app.domains.playback.queries` and `app.infra.db.database` to use that helper instead of `database.py` importing the playback domain.
- Create an infra-owned API token store module for `api_tokens` table persistence.
- Change `app.core.jwt_token` to import the token lookup from the infra store.
- Keep `app.domains.system.api_token_dao` as a compatibility wrapper over the infra store so domain routes do not need behavior changes in this task.

## Out of Scope

- Do not redesign JWT payloads or API token semantics.
- Do not move route handlers or change HTTP response shapes.
- Do not address P1 lifecycle registry in this task.
- Do not consolidate schema DDL sources in this task.

## Verification Plan

- Search: `rg -n "from app\.domains|import app\.domains" app/infra app/core -g "*.py"`.
- Compile: `uv run --with-requirements requirements.txt python -m compileall <changed-python-files>`.
- Focused tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/test_reverse_dependency_boundary.py -v`.
- Full tests: `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v`.

## Verification Results

- Search confirmed no `app.domains` imports remain under `app/infra` or `app/core`.
- Compile verification passed for changed app/test files.
- Focused test passed: `tests/test_reverse_dependency_boundary.py`, 4 tests.
- Full test suite passed: 74 passed, 3 warnings.
