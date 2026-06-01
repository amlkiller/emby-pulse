import sqlite3

from app.infra.db.schema_registry import TABLE_ALTERS, TABLE_SCHEMAS
from app.infra.db.system_store import system_store


def _apply_table_alters(cursor, table_name: str) -> None:
    for alter_sql in TABLE_ALTERS.get(table_name, []):
        try:
            cursor.execute(alter_sql)
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise


def ensure_pro_schema() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(TABLE_SCHEMAS["sys_license"])
        _apply_table_alters(cursor, "sys_license")
        conn.commit()


def replace_license(license_key: str, machine_id: str, status: str = "pro") -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sys_license")
        cursor.execute(
            "INSERT INTO sys_license (license_key, machine_id, status) VALUES (?, ?, ?)",
            (license_key, machine_id, status),
        )
        conn.commit()


def get_license_status():
    return system_store.fetch_one(
        "SELECT license_key, machine_id, status FROM sys_license LIMIT 1"
    )
