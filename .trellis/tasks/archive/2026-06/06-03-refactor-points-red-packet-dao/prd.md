# Refactor Points Red Packet DAO

## Goal

Reduce `app/domains/points/point_dao.py` by extracting red-packet persistence and transaction helpers into a domain-local DAO module while preserving existing behavior and imports.

## Scope

- Add `app/domains/points/red_packet_dao.py` for red-packet log listing, message-id persistence, packet creation, and packet grabbing.
- Move the red-packet DAO functions out of `point_dao.py`.
- Keep `point_dao.py` compatibility exports so existing points routes and notification callers continue to work.
- Do not change red-packet rules, SQL semantics, response dict shapes, route URLs, notification behavior, schema registry ownership, or startup side effects.
- Keep schema-registry source assertions meaningful after the split.

## Verification

- Compile changed Python files and focused point tests with `uv run python -m compileall`.
- Run an import compatibility check through `uv run python -c`.
- Run focused point schema/public facade tests.
- Run the full test suite with `uv run pytest tests/ -v`.
