import datetime
import sqlite3

from app.infra.db.schema_registry import TABLE_ALTERS, TABLE_SCHEMAS
from app.infra.db.system_store import system_store


def ensure_notifications_table() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(TABLE_SCHEMAS["sys_notifications"])
        for alter_sql in TABLE_ALTERS["sys_notifications"]:
            try:
                cursor.execute(alter_sql)
            except sqlite3.OperationalError as exc:
                if "duplicate column" not in str(exc).lower():
                    raise
        conn.commit()


def count_unread_notifications() -> int:
    row = system_store.fetch_one(
        "SELECT COUNT(*) as c FROM sys_notifications WHERE is_read = 0 AND is_cleared = 0"
    )
    return row["c"] if row else 0


def list_notifications(limit: int = 10, include_cleared: bool = False):
    if include_cleared:
        rows = system_store.fetch_all(
            "SELECT * FROM sys_notifications ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
    else:
        rows = system_store.fetch_all(
            "SELECT * FROM sys_notifications WHERE is_cleared = 0 ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )

    return [
        {
            "id": row["id"],
            "type": row["type"],
            "title": row["title"],
            "message": row["message"],
            "is_read": row["is_read"],
            "action_url": row["action_url"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def mark_notifications_read(notification_id: int = None) -> None:
    if notification_id:
        system_store.execute(
            "UPDATE sys_notifications SET is_read = 1 WHERE id = ?",
            (notification_id,),
        )
    else:
        system_store.execute(
            "UPDATE sys_notifications SET is_read = 1 WHERE is_read = 0 AND is_cleared = 0"
        )


def clear_notifications() -> None:
    system_store.execute("DELETE FROM sys_notifications")


def delete_notification(notification_id: int) -> None:
    system_store.execute("DELETE FROM sys_notifications WHERE id = ?", (notification_id,))


def add_system_notification(notify_type: str, title: str, message: str, action_url: str = "") -> None:
    now_str = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
    system_store.execute(
        "INSERT INTO sys_notifications (type, title, message, action_url, created_at) VALUES (?, ?, ?, ?, ?)",
        (notify_type, title, message, action_url, now_str),
    )


def add_sys_notification(notify_type: str, title: str, message: str, action_url: str = "") -> None:
    add_system_notification(notify_type, title, message, action_url)
