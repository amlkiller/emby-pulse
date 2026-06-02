# Point game schema registry bootstrap

## Goal

Continue the P2 schema fact-source cleanup from `docs/架构审计.md` by moving the points game table definitions into `app.infra.db.schema_registry` and routing both system database startup and `app.domains.points.point_dao.ensure_points_schema()` through `schema_bootstrap.ensure_registered_table(...)` for those registry-owned tables.

## Requirements

- Register the points game tables in `SYSTEM_TABLES` and `TABLE_SCHEMAS`:
  - `lottery_tickets`
  - `lottery_results`
  - `lottery_winners`
  - `scratch_cards`
  - `scratch_card_slots`
  - `point_checkin_streak`
  - `point_red_packets`
  - `point_red_packet_logs`
  - `point_transfer_logs`
  - `point_rob_logs`
  - `pk_invitations`
  - `pk_logs`
- Move compatible optional-column upgrades for `scratch_cards`, `point_red_packets`, and `pk_invitations` into `TABLE_ALTERS`.
- Route `_create_system_tables()` startup creation for lottery/scratch-card tables through `_REGISTRY_SYSTEM_INIT_TABLES`.
- Route `ensure_points_schema()` creation for check-in, red packet, transfer, robbery, and PK tables through `ensure_registered_table(...)`.
- Preserve existing point default config insertion and selected DAO behavior.
- Keep unrelated local DDL such as `user_tags`, `tv_series_status`, `media_requests`, invitations, license, Telegram binding compatibility DDL, playback compatibility DDL, and plugin-private tables out of this task.
- Add focused regression coverage proving registry-backed creation, registered ALTER application, preserved point DAO smoke paths, and no local duplicate DDL for the newly registry-owned points game tables.
- Update backend database guidelines with the points game registry contract.

## Acceptance Criteria

- [ ] All listed points game tables are present in `SYSTEM_TABLES` and `TABLE_SCHEMAS`.
- [ ] `TABLE_ALTERS` contains compatible upgrades for:
  - `scratch_cards.chat_id`
  - `scratch_cards.message_id`
  - `point_red_packets.message_id`
  - `pk_invitations.challenger_tg_name`
  - `pk_invitations.target_tg_name`
  - `pk_invitations.command_message_id`
- [ ] `_create_system_tables()` contains no local `CREATE TABLE IF NOT EXISTS` DDL for lottery or scratch-card tables.
- [ ] `ensure_points_schema()` contains no local `CREATE TABLE IF NOT EXISTS` DDL or local ALTER statements for the newly registry-owned point game tables.
- [ ] Fresh temporary system DB initialization creates lottery and scratch-card tables with registered columns.
- [ ] `ensure_points_schema()` creates point game tables with registered columns, applies registered ALTERs to legacy table shapes, inserts default point config, and selected DAO paths still work.
- [ ] Focused tests, compile/import checks, ruff checks for changed files, `git diff --check`, and the full pytest suite pass.

## Definition of Done

- Tests added or updated for changed behavior.
- Changed Python files compile through `uv run --with-requirements requirements.txt`.
- Ruff critical checks pass for changed Python files.
- Full pytest suite passes.
- Work is committed as one coherent points-game schema-registry slice, then the task is archived and journaled.

## Technical Approach

Add registry definitions matching current local DDL and route existing bootstrap paths through `ensure_registered_table(...)`. Keep point default config insertion local to `point_dao` because it is data seeding, not table ownership. Apply compatible optional-column upgrades through `TABLE_ALTERS` so legacy table shapes still upgrade from both startup and DAO bootstrap paths.

## Out of Scope

- Changing point economy defaults, lottery/scratch/PK/red-packet business rules, or route responses.
- Registering unrelated user tag, TV status, media request, invitation, license, Telegram compatibility, playback, or plugin-private tables.
- Centralizing index metadata.
- Decomposing the large `point_dao.py` file beyond the schema bootstrap changes needed here.

## Technical Notes

- `docs/架构审计.md` P2 identifies schema fact-source split as a current cleanup area.
- `tests/test_point_core_schema_bootstrap_registry.py` currently asserts point game tables remain local; this should be advanced to assert registry ownership for the full point game schema slice.
- `app.infra.db.database._create_system_tables()` currently owns startup DDL for `lottery_*` and `scratch_*` tables.
- `app.domains.points.point_dao.ensure_points_schema()` currently owns local DDL for `point_checkin_streak`, `point_red_packets`, `point_red_packet_logs`, `point_transfer_logs`, `point_rob_logs`, `pk_invitations`, and `pk_logs`, plus local ALTERs for `point_red_packets` and `pk_invitations`.
