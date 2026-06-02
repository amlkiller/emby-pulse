# Remove Pass-Through Wrapper Functions

## Goal

Inspect the Python project and remove middle-layer wrapper functions that do not add semantic value. Callers should import and call the module that performs the real work when the intermediate function only forwards arguments and returns the result.

## Scope

- Backend Python code under `app/`.
- Tests under `tests/` that enforce import boundaries or wrapper behavior.
- Trellis task context files for this work.

## Requirements

- Remove functions that only delegate to another function, method, DAO, query, or service without validation, permission checks, normalization, error handling, lazy runtime lookup, orchestration, cache ownership, response mapping, or compatibility purpose.
- Update all call sites to import the real implementation directly.
- Keep public facades that add meaningful boundary semantics, such as auth/session checks, policy decisions, payload normalization, lazy dependency resolution, exception handling, cross-call orchestration, or intentional compatibility re-exports.
- Preserve runtime behavior, route URLs, response shapes, and database behavior.
- Add or update focused tests when boundary expectations change.
- Run verification through `uv run`.

## Completion Evidence

- Static search/AST review identifies no remaining obvious no-op pass-through wrappers in touched boundary areas.
- Relevant compile/import checks pass.
- Focused tests for changed boundaries pass.
- A task commit contains only this task's coherent changes.
