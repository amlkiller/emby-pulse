from app.infra.db.system_store import system_store


def ensure_emby_restart_history_table() -> None:
    system_store.execute(
        """
        CREATE TABLE IF NOT EXISTS emby_restart_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT NOT NULL,
            mode TEXT,
            success INTEGER,
            detail TEXT
        )
        """
    )


def list_emby_restart_history(limit: int = 20):
    ensure_emby_restart_history_table()
    return system_store.fetch_all(
        """
        SELECT time, mode, success, detail
        FROM emby_restart_history
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )


def create_emby_restart_history(record: dict) -> None:
    ensure_emby_restart_history_table()
    system_store.execute(
        """
        INSERT INTO emby_restart_history (time, mode, success, detail)
        VALUES (?, ?, ?, ?)
        """,
        (
            record["time"],
            record.get("mode", ""),
            1 if record["success"] else 0,
            record.get("detail", ""),
        ),
    )
