# Refactor Domain Monolith Slice

## Context

`docs/架构审计.md` identifies P2 architecture debt: migrated domain modules still contain large mixed-responsibility files. The recommended remediation is small, behavior-preserving slices rather than broad rewrites.

## Goal

Refactor one maintainable slice from a large `app/domains/` module into a named helper/service/query module while preserving existing routes, response shapes, imports, and runtime behavior.

## Scope

- Target a high-value large domain file listed in the architecture audit.
- Move one coherent responsibility at a time into a domain-local module.
- Keep public HTTP route paths and response compatibility unchanged.
- Do not deepen cross-domain imports into private modules.
- Add or run focused verification for the changed files.
- Commit this task's changes when verification passes.

## Non-goals

- No broad rewrite of notification bot services.
- No route contract changes.
- No schema or lifecycle changes in this task unless required by the slice.

## Acceptance Criteria

- A large domain file is smaller and delegates one named responsibility to a new or existing domain-local module.
- The extracted module has a clear responsibility name aligned with Trellis backend directory guidance.
- Existing behavior is preserved by compile/import checks and the relevant test suite.
- The work is committed with a focused refactor commit.
