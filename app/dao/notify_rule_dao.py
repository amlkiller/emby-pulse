from app.infra.db.system_store import system_store


def ensure_bot_notify_mutes_table() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS bot_notify_mutes (
                user_id TEXT,
                event_type TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, event_type)
            )"""
        )
        conn.commit()


def list_bot_notify_mutes():
    return system_store.fetch_all("SELECT user_id, event_type FROM bot_notify_mutes")


def replace_bot_notify_mutes(playback_users, login_users) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM bot_notify_mutes")
        cursor.executemany(
            "INSERT INTO bot_notify_mutes (user_id, event_type) VALUES (?, ?)",
            [(uid, "playback") for uid in playback_users],
        )
        cursor.executemany(
            "INSERT INTO bot_notify_mutes (user_id, event_type) VALUES (?, ?)",
            [(uid, "login") for uid in login_users],
        )
        conn.commit()
