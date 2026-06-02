import json
import time

from app.infra.db.schema_bootstrap import ensure_registered_table
from app.infra.db.system_store import system_store

SESSION_TABLE = "sessions"


def ensure_session_table() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        ensure_registered_table(cursor, SESSION_TABLE)
        conn.commit()


def create_session(session_id: str, data: dict, created_at: float, expires_at: float) -> None:
    data_json = json.dumps(data or {}, ensure_ascii=False)
    system_store.execute(
        f"INSERT INTO {SESSION_TABLE} (session_id, data, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (session_id, data_json, created_at, expires_at),
    )


def get_session(session_id: str, now: float, absolute_cutoff: float):
    return system_store.fetch_one(
        f"""
        SELECT data, created_at FROM {SESSION_TABLE}
        WHERE session_id = ? AND expires_at > ? AND created_at > ?
        """,
        (session_id, now, absolute_cutoff),
    )


def update_session(session_id: str, data: dict) -> None:
    data_json = json.dumps(data, ensure_ascii=False)
    system_store.execute(
        f"UPDATE {SESSION_TABLE} SET data = ? WHERE session_id = ?",
        (data_json, session_id),
    )


def delete_session(session_id: str) -> None:
    system_store.execute(f"DELETE FROM {SESSION_TABLE} WHERE session_id = ?", (session_id,))


def clear_sessions_if_table_exists():
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (SESSION_TABLE,))
        if not cursor.fetchone():
            return None

        cursor.execute(f"DELETE FROM {SESSION_TABLE}")
        deleted_count = cursor.rowcount
        conn.commit()
        return deleted_count


def cleanup_expired_sessions(now: float) -> int:
    return system_store.execute(f"DELETE FROM {SESSION_TABLE} WHERE expires_at < ?", (now,))
