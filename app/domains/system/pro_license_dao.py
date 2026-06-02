from app.infra.db.schema_bootstrap import ensure_registered_table
from app.infra.db.system_store import system_store


def ensure_pro_schema() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        ensure_registered_table(cursor, "sys_license")
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
