# Refactor Points PK DAO

## Goal

Reduce `app/domains/points/point_dao.py` by extracting user PK invitation persistence and transaction helpers into a domain-local DAO module while preserving existing behavior and imports.

## Requirements

- Add `app/domains/points/pk_dao.py` for PK invitation listing, status updates, rejection/cleanup, message-id persistence, invitation creation, and invitation acceptance.
- Move PK invitation DAO functions out of `point_dao.py`.
- Keep `point_dao.py` compatibility exports so existing points routes and notification callers continue to work.
- Do not change PK rules, SQL semantics, response dict shapes, route URLs, notification behavior, schema registry ownership, or startup side effects.
- Keep schema-registry source assertions meaningful after the split.

## Acceptance Criteria

- [ ] `point_dao.py` no longer contains direct `pk_invitations` / `pk_logs` business transaction bodies except schema bootstrap table names and compatibility imports.
- [ ] Existing callers can still access PK helpers from `app.domains.points.point_dao`.
- [ ] The new `pk_dao.py` owns the moved PK persistence functions and imports only domain-local/runtime dependencies needed for those functions.
- [ ] Focused schema/public facade tests pass.
- [ ] Full test suite passes before committing.

## Definition of Done

- Compile changed Python files with `uv run python -m compileall`.
- Run an import compatibility check through `uv run python -c`.
- Run focused point schema/public facade tests.
- Run the full test suite with `uv run pytest tests/ -v`.
- Commit the code/test slice, archive the Trellis task, and record the session journal.

## Technical Approach

Use the same compatibility-preserving pattern already used for `lottery_dao.py` and `red_packet_dao.py`: move the PK helper bodies into a sibling `*_dao.py` file, import those names back into `point_dao.py`, and update the schema-bootstrap source scan to include the new file.

## Out of Scope

- Changing PK gameplay rules, random roll behavior, tax calculation, expiry semantics, or response payload keys.
- Changing notification bot or points router call sites to import `pk_dao` directly.
- Moving transfer, robbery, redemption, check-in, or generic point log helpers.
- Refactoring cross-domain public service boundaries.

## Technical Notes

- Architecture audit target: `docs/架构审计.md` P2 item 5, small behavior-preserving splits of large domain files.
- Applicable specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`.
- Existing compatibility pattern: `app/domains/points/lottery_dao.py` and `app/domains/points/red_packet_dao.py`.
