from app.infra.db.system_store import system_store


def ensure_calendar_notify_config_table() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS calendar_notify_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                enabled INTEGER DEFAULT 0,
                notify_time TEXT DEFAULT '09:00',
                channels TEXT DEFAULT '["tg_bot"]',
                tg_chat_id TEXT,
                wecom_touser TEXT DEFAULT '@all',
                last_sent TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        cursor.execute("INSERT OR IGNORE INTO calendar_notify_config (id, enabled) VALUES (1, 0)")
        conn.commit()


def get_calendar_notify_config():
    return system_store.fetch_one("SELECT * FROM calendar_notify_config WHERE id = 1")


def save_calendar_notify_config(
    enabled: bool,
    notify_time: str,
    channels: str,
    tg_chat_id: str,
    wecom_touser: str,
) -> None:
    system_store.execute(
        """
        UPDATE calendar_notify_config
        SET enabled = ?,
            notify_time = ?,
            channels = ?,
            tg_chat_id = ?,
            wecom_touser = ?,
            updated_at = datetime('now', 'localtime')
        WHERE id = 1
        """,
        (1 if enabled else 0, notify_time, channels, tg_chat_id, wecom_touser),
    )


def mark_calendar_notify_sent() -> None:
    system_store.execute(
        "UPDATE calendar_notify_config SET last_sent = datetime('now', 'localtime') WHERE id = 1"
    )
