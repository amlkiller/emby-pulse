import os
import sqlite3

from app.core.config import DB_PATH
from app.infra.db.schema_bootstrap import ensure_playback_table
from app.infra.db.row import to_data_row


def get_local_playback_db_path() -> str:
    data_dir = os.path.dirname(DB_PATH)
    os.makedirs(data_dir, exist_ok=True)
    return DB_PATH


def _ensure_playback_ip_columns(cursor) -> None:
    ensure_playback_table(cursor)


def fetch_playback_ip_rows(item_ids, user_ids):
    if not item_ids or not user_ids:
        return []

    local_db_path = get_local_playback_db_path()
    if not os.path.exists(local_db_path):
        return []

    conn = sqlite3.connect(local_db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        placeholders = ",".join(["?"] * len(item_ids))
        user_placeholders = ",".join(["?"] * len(user_ids))
        cursor.execute(
            f"""
            SELECT UserId, ItemId, RemoteEndPoint, Location, ISP
            FROM PlaybackActivity
            WHERE ItemId IN ({placeholders}) AND UserId IN ({user_placeholders})
            AND RemoteEndPoint IS NOT NULL AND RemoteEndPoint != ''
            """,
            list(item_ids) + list(user_ids),
        )
        return [to_data_row(row) for row in cursor.fetchall()]
    finally:
        conn.close()


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
