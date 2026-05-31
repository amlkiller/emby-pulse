import json
from typing import Optional

from app.infra.db.system_store import system_store


def ensure_smart_collection_tables() -> None:
    with system_store.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS smart_collections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                icon TEXT DEFAULT 'fa-layer-group',
                icon_color TEXT DEFAULT 'from-purple-500 to-pink-500',
                source_type TEXT DEFAULT 'tmdb_trending',
                source_config TEXT DEFAULT '{}',
                min_rating REAL DEFAULT 7.0,
                update_mode TEXT DEFAULT 'incremental',
                is_enabled INTEGER DEFAULT 1,
                last_sync TEXT,
                last_count INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS smart_collection_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                tmdb_id TEXT,
                title TEXT,
                sort_order INTEGER DEFAULT 0,
                added_at TEXT,
                FOREIGN KEY (collection_id) REFERENCES smart_collections(id) ON DELETE CASCADE,
                UNIQUE(collection_id, item_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS smart_collection_sync_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection_id INTEGER,
                action TEXT,
                status TEXT,
                message TEXT,
                count INTEGER DEFAULT 0,
                created_at TEXT
            )
            """
        )
        conn.commit()


def list_smart_collections():
    ensure_smart_collection_tables()
    return system_store.fetch_all(
        """
        SELECT c.*,
               (SELECT COUNT(*) FROM smart_collection_items WHERE collection_id = c.id) as item_count
        FROM smart_collections c
        ORDER BY c.updated_at DESC
        """
    )


def get_smart_collection(collection_id: int):
    ensure_smart_collection_tables()
    return system_store.fetch_one("SELECT * FROM smart_collections WHERE id = ?", (collection_id,))


def list_smart_collection_items(collection_id: int):
    ensure_smart_collection_tables()
    return system_store.fetch_all(
        """
        SELECT * FROM smart_collection_items
        WHERE collection_id = ?
        ORDER BY sort_order, added_at DESC
        """,
        (collection_id,),
    )


def create_smart_collection(data: dict, now_str: str) -> int:
    ensure_smart_collection_tables()
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO smart_collections
            (name, icon, icon_color, source_type, source_config, min_rating, update_mode, is_enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("name", ""),
                data.get("icon", "fa-layer-group"),
                data.get("icon_color", "from-purple-500 to-pink-500"),
                data.get("source_type", "tmdb_movie_trending"),
                json.dumps(data.get("source_config", {})),
                float(data.get("min_rating") if data.get("min_rating") is not None else 7.0),
                data.get("update_mode", "incremental"),
                1 if data.get("is_enabled", True) else 0,
                now_str,
                now_str,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def update_smart_collection(collection_id: int, data: dict, now_str: str) -> None:
    ensure_smart_collection_tables()
    system_store.execute(
        """
        UPDATE smart_collections SET
        name = ?, icon = ?, icon_color = ?, source_type = ?, source_config = ?,
        min_rating = ?, update_mode = ?, is_enabled = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            data.get("name", ""),
            data.get("icon", "fa-layer-group"),
            data.get("icon_color", "from-purple-500 to-pink-500"),
            data.get("source_type", "tmdb_movie_trending"),
            json.dumps(data.get("source_config", {})),
            float(data.get("min_rating") if data.get("min_rating") is not None else 7.0),
            data.get("update_mode", "incremental"),
            1 if data.get("is_enabled", True) else 0,
            now_str,
            collection_id,
        ),
    )


def delete_smart_collection(collection_id: int) -> Optional[str]:
    ensure_smart_collection_tables()
    row = system_store.fetch_one("SELECT name FROM smart_collections WHERE id = ?", (collection_id,))
    if not row:
        return None
    system_store.execute("DELETE FROM smart_collection_items WHERE collection_id = ?", (collection_id,))
    system_store.execute("DELETE FROM smart_collections WHERE id = ?", (collection_id,))
    return row["name"]


def list_smart_collection_logs(limit: int = 50):
    ensure_smart_collection_tables()
    return system_store.fetch_all(
        """
        SELECT l.*, c.name as collection_name
        FROM smart_collection_sync_logs l
        LEFT JOIN smart_collections c ON l.collection_id = c.id
        ORDER BY l.created_at DESC
        LIMIT ?
        """,
        (limit,),
    )


def add_smart_collection_log(collection_id: int, action: str, status: str, message: str, count: int, now_str: str) -> None:
    ensure_smart_collection_tables()
    system_store.execute(
        """
        INSERT INTO smart_collection_sync_logs (collection_id, action, status, message, count, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (collection_id, action, status, message, count, now_str),
    )


def list_enabled_smart_collections():
    ensure_smart_collection_tables()
    return system_store.fetch_all("SELECT * FROM smart_collections WHERE is_enabled = 1")


def set_smart_collection_sync_state(collection_id: int, now_str: str, count: int) -> None:
    ensure_smart_collection_tables()
    system_store.execute(
        "UPDATE smart_collections SET last_sync = ?, last_count = ?, updated_at = ? WHERE id = ?",
        (now_str, count, now_str, collection_id),
    )


def replace_smart_collection_items(collection_id: int, item_ids, now_str: str) -> None:
    ensure_smart_collection_tables()
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM smart_collection_items WHERE collection_id = ?", (collection_id,))
        for idx, item_id in enumerate(item_ids):
            cursor.execute(
                """
                INSERT INTO smart_collection_items (collection_id, item_id, sort_order, added_at)
                VALUES (?, ?, ?, ?)
                """,
                (collection_id, item_id, idx, now_str),
            )
        conn.commit()
