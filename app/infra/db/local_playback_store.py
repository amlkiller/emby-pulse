import os
import sqlite3

from app.core.config import DB_PATH


WEBHOOK_PLAYBACK_SCHEMA = """CREATE TABLE IF NOT EXISTS PlaybackActivity (
    Id INTEGER PRIMARY KEY AUTOINCREMENT,
    UserId TEXT,
    UserName TEXT,
    ItemId TEXT,
    ItemName TEXT,
    PlayDuration INTEGER,
    DateCreated DATETIME DEFAULT CURRENT_TIMESTAMP,
    Client TEXT,
    DeviceName TEXT,
    RemoteEndPoint TEXT,
    ItemType TEXT,
    Location TEXT,
    ISP TEXT
)"""


def get_local_playback_db_path() -> str:
    data_dir = os.path.dirname(DB_PATH)
    os.makedirs(data_dir, exist_ok=True)
    return DB_PATH


def _ensure_playback_ip_columns(cursor) -> None:
    cursor.execute(WEBHOOK_PLAYBACK_SCHEMA)
    for column_name in ("RemoteEndPoint", "ItemType", "Location", "ISP"):
        try:
            cursor.execute(f"ALTER TABLE PlaybackActivity ADD COLUMN {column_name} TEXT")
        except Exception:
            pass


def insert_webhook_playback_ip_record(
    user_id: str,
    user_name: str,
    item_id: str,
    item_name: str,
    date_created: str,
    client: str,
    device_name: str,
    remote_endpoint: str,
    location: str,
    isp: str,
) -> None:
    conn = sqlite3.connect(get_local_playback_db_path())
    try:
        cursor = conn.cursor()
        _ensure_playback_ip_columns(cursor)

        cursor.execute(
            """
            INSERT INTO PlaybackActivity
            (UserId, UserName, ItemId, ItemName, PlayDuration, DateCreated, Client, DeviceName, RemoteEndPoint, Location, ISP)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                user_name,
                item_id,
                item_name,
                0,
                date_created or "now",
                client,
                device_name,
                remote_endpoint,
                location,
                isp,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def insert_bot_playback_history_record(
    user_id: str,
    user_name: str,
    item_id: str,
    item_name: str,
    item_type: str,
    client: str,
    device_name: str,
    remote_endpoint: str,
    location: str,
    isp: str,
) -> None:
    conn = sqlite3.connect(get_local_playback_db_path())
    try:
        cursor = conn.cursor()
        _ensure_playback_ip_columns(cursor)
        cursor.execute(
            """
            INSERT INTO PlaybackActivity
            (UserId, UserName, ItemId, ItemName, ItemType, PlayDuration, Client, DeviceName, RemoteEndPoint, Location, ISP)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                user_name,
                item_id,
                item_name,
                item_type,
                0,
                client,
                device_name,
                remote_endpoint,
                location,
                isp,
            ),
        )
        conn.commit()
    finally:
        conn.close()
