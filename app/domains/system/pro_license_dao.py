from app.infra.db.system_store import system_store


def ensure_pro_schema() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS sys_license (
                license_key TEXT,
                machine_id TEXT,
                pro_token TEXT,
                status TEXT DEFAULT 'pro',
                expire_date DATETIME,
                last_checked DATETIME DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        for column in [
            "pro_token TEXT",
            "expire_date DATETIME",
            "last_checked DATETIME DEFAULT CURRENT_TIMESTAMP",
            "max_devices INTEGER",
            "current_devices INTEGER",
        ]:
            try:
                cursor.execute(f"ALTER TABLE sys_license ADD COLUMN {column}")
            except Exception:
                pass
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
