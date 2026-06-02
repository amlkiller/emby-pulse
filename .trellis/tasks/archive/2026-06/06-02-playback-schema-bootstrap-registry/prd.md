# Playback Schema Bootstrap Registry

## Goal

Continue the architecture audit refactor by removing local `PlaybackActivity` schema copies from startup and local playback fallback bootstraps.

## Scope

- Add an infra bootstrap helper for registry-backed `PlaybackActivity` creation using `PLAYBACK_SCHEMA` plus `TABLE_ALTERS["PlaybackActivity"]`.
- Route `app.infra.db.database.init_db()` playback compatibility initialization through that helper.
- Route `app.infra.db.local_playback_store` fallback initialization through that helper.
- Register the fallback-required `ItemType` compatible column so bot/local playback history writes keep working after centralized bootstrap.
- Update focused regression tests and database spec guidance.

## Non-Goals

- Do not change playback query behavior or API-vs-SQLite data source selection.
- Do not redesign playback reporting table shape beyond centralizing existing compatible columns.
- Do not refactor the large playback stats/router modules in this slice.

## Acceptance Criteria

- `database.init_db()` no longer contains local `CREATE TABLE IF NOT EXISTS PlaybackActivity` or local `ALTER TABLE PlaybackActivity ADD COLUMN` copies.
- `local_playback_store` no longer contains a local playback table DDL string or local playback `ALTER TABLE` loop.
- Fresh and legacy `PlaybackActivity` tables receive registered compatible columns, including `RemoteEndPoint`, `Location`, `ISP`, `ClientName`, and `ItemType`.
- Webhook and bot local playback insert paths work against a temporary local playback database.
- Focused tests, compile, ruff, `git diff --check`, and full pytest pass in one consolidated verification pass.
