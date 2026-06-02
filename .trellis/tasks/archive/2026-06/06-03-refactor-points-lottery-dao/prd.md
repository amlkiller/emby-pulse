# Refactor Points Lottery DAO

## Goal

Reduce `app/domains/points/point_dao.py` by extracting lottery persistence and draw helpers into a domain-local DAO module while preserving existing behavior and imports.

## Scope

- Add `app/domains/points/lottery_dao.py` for lottery table bootstrap and lottery ticket/result/pool functions.
- Move lottery table bootstrap from `point_dao.py` to the new module.
- Move lottery DAO functions out of `point_dao.py`, including ticket listing, ticket purchase, draw context/result persistence, pool info, and result listing.
- Keep `point_dao.py` compatibility exports so existing callers using `app.domains.points.point_dao` continue to work.
- Do not change lottery rules, SQL semantics, response dict shapes, route URLs, notification behavior, schema registry ownership, or startup side effects.

## Verification

- Compile changed Python files and focused point tests with `uv run python -m compileall`.
- Run an import compatibility check through `uv run python -c`.
- Run focused point schema/public facade tests.
- Run the full test suite with `uv run pytest tests/ -v`.
