# Database Guidelines

> Database patterns and conventions for this project.

---

## Scenario: First-Stage Database Boundary

### 1. Scope / Trigger

- Trigger: database infrastructure refactor that starts removing `query_db()` from representative modules.
- Applies to new backend code that reads/writes EmbyPulse system data or playback reporting data.
- First-stage sample modules are `app/routers/history.py` and `app/routers/api_tokens.py`.

### 2. Signatures

- `app.infra.db.system_store.system_store.fetch_all(sql: str, params=()) -> list[DataRow]`
- `app.infra.db.system_store.system_store.fetch_one(sql: str, params=()) -> DataRow | None`
- `app.infra.db.system_store.system_store.execute(sql: str, params=()) -> int`
- `app.infra.db.playback_store.playback_store.query(sql: str, params=(), one: bool = False) -> list[DataRow] | DataRow | None`
- `app.infra.db.playback_store.get_playback_column_name() -> str`
- Scenario modules live in `app/queries/*_queries.py` and `app/dao/*_dao.py` during the transition.

### 3. Contracts

- System database access must go through `system_store` or a DAO that wraps it.
- Playback reporting access must go through `playback_store` or a query service that wraps it.
- `playback_store` owns the SQLite/API data-source switch for `PlaybackActivity`.
- Route modules should call scenario functions such as `history_queries` or `api_token_dao`, not open SQLite connections directly.
- Return rows use `DataRow`, which supports dict-style access, `.get()`, integer index access, and case-insensitive keys for compatibility with legacy callers.

### 4. Validation & Error Matrix

- Missing playback database file -> `playback_store.query(...)` returns `None` and logs the same user-facing warning style as the legacy path.
- Emby API passthrough failure -> `playback_store.query(...)` falls back to SQLite when possible.
- System database write failure -> DAO exception bubbles to the router, where existing `HTTPException(... safe_error_message(...))` handling is preserved.
- Empty SELECT result -> `fetch_all` returns `[]`; `fetch_one` returns `None`.

### 5. Good/Base/Bad Cases

- Good: `api_tokens.py` calls `api_token_dao.create_api_token_record(...)` and keeps HTTP response shape unchanged.
- Base: `history.py` calls `history_queries.count_history(...)` and still returns the same pagination payload.
- Bad: a router imports `query_db`, `SYSTEM_DB_PATH`, or `sqlite3` only to run route-local SQL.

### 6. Tests Required

- Compile/import check for new infra, query, DAO, and migrated router modules.
- Full existing pytest suite after representative migration.
- When adding a new migrated module, assert route response fields stay compatible with the pre-migration shape.

### 7. Wrong vs Correct

#### Wrong

```python
from app.core.database import query_db

rows = query_db("SELECT * FROM PlaybackActivity LIMIT 20")
```

#### Correct

```python
from app.queries.history_queries import fetch_history_rows

rows = fetch_history_rows(select_fields, where_sql, params, limit, offset)
```

#### Wrong

```python
import sqlite3
from app.core.database import SYSTEM_DB_PATH

conn = sqlite3.connect(SYSTEM_DB_PATH)
```

#### Correct

```python
from app.dao.api_token_dao import list_api_tokens

tokens = list_api_tokens(user_id)
```

---

## Migrations

- `app.infra.db.schema_registry` is the new import point for schema metadata during migration.
- Existing schema definitions still delegate to `app.core.db_schemas` until ownership is fully moved.
- `app.infra.db.migration_service` is the new boundary for migration/health orchestration and currently delegates to existing implementations.

---

## Common Mistakes

- Do not add new `query_db()` usage in migrated modules.
- Do not hide playback API passthrough inside system database helpers.
- Do not mix route response changes into database access migration.
- Do not migrate plugin database access in the first stage; design the boundary so plugin state/config/log tables can migrate later.
