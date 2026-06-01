# Move App Version Out of Main

## Goal

Address P1 item 1 from `docs/架构审计.md`: remove domain imports of `app.main` that only exist to read `APP_VERSION`.

## Requirements

- Create a side-effect-free module for the runtime version, such as `app/shared/version.py`.
- Move `APP_VERSION` out of `app/main.py` into that module.
- Keep `app.main.APP_VERSION` available for compatibility by importing it from the new module.
- Update domain modules that currently import `APP_VERSION` from `app.main`:
  - `app/domains/system/views.py`
  - `app/domains/notifications/notify_admin.py`
  - `app/domains/system/audit.py`
- Preserve template context values and the current version string.
- Add a regression test proving importing those domain modules does not trigger `app.main.create_app()`.
- Keep unrelated active PRD/archive cleanup out of scope.

## Acceptance Criteria

- [x] `APP_VERSION` is defined in a side-effect-free module outside `app/main.py`.
- [x] No domain module imports `app.main` for version access.
- [x] `app.main.APP_VERSION` remains available and equals the shared version.
- [x] A regression test proves domain imports do not call `app.main.create_app()`.
- [x] Compile/import verification passes through `uv run --with-requirements requirements.txt`.
- [x] Existing tests still pass.

## Technical Approach

Use a conservative dependency-direction fix. Do not alter startup behavior in `app/main.py` beyond changing where the version constant is sourced from. This keeps runtime behavior stable while removing the domain-to-entrypoint dependency identified by the audit.

## Out of Scope

- Do not refactor the `app = create_app()` import-time behavior in `app/main.py` in this task.
- Do not address other P1 items such as infra/core reverse dependencies or lifecycle registry.
- Do not archive old completed tasks in this batch.

## Verification Plan

- Search: `rg -n "from app\.main import|import app\.main|APP_VERSION" app tests`.
- Compile: `uv run --with-requirements requirements.txt python -m compileall app/main.py app/shared/version.py app/domains/system/views.py app/domains/notifications/notify_admin.py app/domains/system/audit.py tests/test_app_version_boundary.py`.
- Test: `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v`.

## Verification Results

- Search confirmed no domain imports `app.main` for version access.
- Focused test: `tests/test_app_version_boundary.py` passed, 2 tests.
- Compile verification passed for changed app/test files.
- Full test suite passed: 70 passed, 3 warnings.
