# Refactor Points DAO Slice

## Context

`docs/架构审计.md` identifies `app/domains/points/point_dao.py` as one of the large mixed-responsibility domain files. The backend directory spec recommends small behavior-preserving slices into named DAO/query/service modules.

## Goal

Extract one coherent points subdomain persistence slice from `point_dao.py` into a domain-local module while preserving existing external call paths and behavior.

## Scope

- Target `app/domains/points/point_dao.py`.
- Move one cohesive DAO responsibility into a named `*_dao.py` module.
- Keep `point_dao.py` compatibility exports so routers, notifications, plugins, and tests can keep importing the same function names.
- Do not change route URLs, response shapes, schema definitions, or point economy behavior.
- Use locked `uv run` verification.
- Commit the completed work and archive/record the Trellis task.

## Acceptance Criteria

- `point_dao.py` is smaller and delegates one named responsibility to a domain-local DAO module.
- Existing callers through `point_dao` continue to work.
- Focused compile/import/tests pass.
- Full `uv run pytest tests/ -v` passes before commit.
