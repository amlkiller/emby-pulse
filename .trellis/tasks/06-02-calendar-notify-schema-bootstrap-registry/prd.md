# Refactor Calendar Notify Schema Bootstrap Through Registry

## Problem

`docs/架构审计.md` identifies split database schema fact sources as an active P2 risk. `calendar_notify_config` is still created locally in `app/domains/notifications/calendar_notify_dao.py`, so table shape can drift from registry-backed initialization and repair paths.

## Scope

- Register `calendar_notify_config` in `app/infra/db/schema_registry.py`.
- Change `calendar_notify_dao.ensure_calendar_notify_config_table()` to create the table through the registry helper.
- Preserve the existing default singleton row behavior.
- Add focused regression tests for table creation, DAO read/write paths, and source-boundary checks.

## Non-Goals

- Do not change notification scheduling behavior.
- Do not change API response shapes in `calendar_notify.py`.
- Do not migrate unrelated notification announcement tables.
- Do not migrate plugin database access.

## Acceptance Criteria

- [x] `calendar_notify_config` is present in `SYSTEM_TABLES` and `TABLE_SCHEMAS`.
- [x] `calendar_notify_dao` creates `calendar_notify_config` from registry metadata and preserves `INSERT OR IGNORE` default row behavior.
- [x] Calendar notify config read/save/mark-sent DAO paths work after registry bootstrap.
- [x] Focused tests assert no local duplicate `CREATE TABLE IF NOT EXISTS calendar_notify_config` remains in `calendar_notify_dao.py`.
- [x] Full pytest suite passes, plus compile/import checks for changed Python files.
