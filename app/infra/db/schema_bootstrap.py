from typing import Optional

from app.infra.db.schema_registry import PLAYBACK_SCHEMA, TABLE_ALTERS, TABLE_SCHEMAS


def column_name_from_alter(alter_sql: str) -> str:
    return alter_sql.split("ADD COLUMN ", 1)[1].split(" ", 1)[0]


def table_columns(cursor, table_name: str) -> set[str]:
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {column[1] for column in cursor.fetchall()}


def registered_alter_columns(table_name: str) -> set[str]:
    return {
        column_name_from_alter(alter_sql)
        for alter_sql in TABLE_ALTERS.get(table_name, [])
    }


def ensure_registered_table(cursor, table_name: str, only_columns: Optional[set[str]] = None) -> set[str]:
    cursor.execute(TABLE_SCHEMAS[table_name])
    columns = table_columns(cursor, table_name)

    return apply_registered_alters(cursor, table_name, columns, only_columns)


def apply_registered_alters(
    cursor,
    table_name: str,
    columns: set[str],
    only_columns: Optional[set[str]] = None,
) -> set[str]:
    for alter_sql in TABLE_ALTERS.get(table_name, []):
        column_name = column_name_from_alter(alter_sql)
        if only_columns is not None and column_name not in only_columns:
            continue
        if column_name not in columns:
            cursor.execute(alter_sql)
            columns.add(column_name)

    return columns


def ensure_playback_table(cursor, only_columns: Optional[set[str]] = None) -> set[str]:
    cursor.execute(PLAYBACK_SCHEMA)
    columns = table_columns(cursor, "PlaybackActivity")
    return apply_registered_alters(cursor, "PlaybackActivity", columns, only_columns)
