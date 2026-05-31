from app.infra.db.system_store import system_store


def ensure_keep_alive_violations_table() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS keep_alive_violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                user_name TEXT NOT NULL,
                year_month TEXT NOT NULL,
                hours REAL DEFAULT 0,
                days INTEGER DEFAULT 0,
                min_hours REAL DEFAULT 0,
                min_days INTEGER DEFAULT 0,
                action TEXT DEFAULT 'warn',
                disabled INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, year_month)
            )
            """
        )
        try:
            cursor.execute("ALTER TABLE keep_alive_violations ADD COLUMN action TEXT DEFAULT 'warn'")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE keep_alive_violations ADD COLUMN disabled INTEGER DEFAULT 0")
        except Exception:
            pass
        conn.commit()


def save_keep_alive_violation(
    user_id: str,
    user_name: str,
    year_month: str,
    hours,
    days,
    min_hours,
    min_days,
    action: str,
    disabled: bool,
) -> None:
    system_store.execute(
        """
        INSERT OR REPLACE INTO keep_alive_violations
        (user_id, user_name, year_month, hours, days, min_hours, min_days, action, disabled)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, user_name, year_month, hours, days, min_hours, min_days, action, 1 if disabled else 0),
    )


def list_keep_alive_months():
    return system_store.fetch_all("SELECT DISTINCT year_month FROM keep_alive_violations ORDER BY year_month DESC")


def list_keep_alive_violations(year_month: str, limit: int, offset: int):
    return system_store.fetch_all(
        """
        SELECT * FROM keep_alive_violations
        WHERE year_month = ?
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        (year_month, limit, offset),
    )


def count_keep_alive_violations(year_month: str = None) -> int:
    if year_month:
        row = system_store.fetch_one(
            "SELECT COUNT(*) as count FROM keep_alive_violations WHERE year_month = ?",
            (year_month,),
        )
    else:
        row = system_store.fetch_one("SELECT COUNT(*) as count FROM keep_alive_violations")
    return row["count"] if row else 0


def count_keep_alive_disabled() -> int:
    row = system_store.fetch_one("SELECT COUNT(*) as count FROM keep_alive_violations WHERE disabled = 1")
    return row["count"] if row else 0


def count_keep_alive_unique_users() -> int:
    row = system_store.fetch_one("SELECT COUNT(DISTINCT user_id) as count FROM keep_alive_violations")
    return row["count"] if row else 0


def update_keep_alive_violation_disabled(violation_id: int, disabled: bool) -> None:
    system_store.execute(
        "UPDATE keep_alive_violations SET disabled = ? WHERE id = ?",
        (1 if disabled else 0, violation_id),
    )
