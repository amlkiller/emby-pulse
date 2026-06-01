from app.infra.db.schema_registry import TABLE_SCHEMAS
from app.infra.db.system_store import system_store


def ensure_bot_notify_mutes_table() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(TABLE_SCHEMAS["bot_notify_mutes"])
        conn.commit()


def list_bot_notify_mutes():
    return system_store.fetch_all("SELECT user_id, event_type FROM bot_notify_mutes")


def is_bot_notify_muted(user_id, event_type) -> bool:
    row = system_store.fetch_one(
        "SELECT 1 FROM bot_notify_mutes WHERE user_id = ? AND event_type = ?",
        (user_id, event_type),
    )
    return bool(row)


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
