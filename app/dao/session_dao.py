import json
import time

from app.infra.db.system_store import system_store

SESSION_TABLE = "sessions"


def ensure_session_table() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {SESSION_TABLE} (
                session_id TEXT PRIMARY KEY,
                data TEXT NOT NULL DEFAULT '{{}}',
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )
            """
        )
        try:
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_sessions_expires ON {SESSION_TABLE}(expires_at)")
        except Exception:
            pass
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


def cleanup_expired_sessions(now: float) -> int:
    return system_store.execute(f"DELETE FROM {SESSION_TABLE} WHERE expires_at < ?", (now,))
