"""
Database Session Management
Replaces SessionMiddleware, no SECRET_KEY needed, more secure
"""
import secrets
import time
import json
import sqlite3
from typing import Optional, Any, Dict
from app.core.config import SYSTEM_DB_PATH

SESSION_TABLE = "sessions"
SESSION_COOKIE_NAME = "session_id"
SESSION_MAX_AGE = 24 * 3600  # 24小时（空闲超时）
SESSION_ABSOLUTE_MAX_AGE = 7 * 24 * 3600  # 7天（绝对超时）


def _get_system_conn():
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_session_table():
    conn = _get_system_conn()
    cursor = conn.cursor()
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS {SESSION_TABLE} (
        session_id TEXT PRIMARY KEY,
        data TEXT NOT NULL DEFAULT '{{}}',
        created_at REAL NOT NULL,
        expires_at REAL NOT NULL
    )
    """)
    try:
        cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_sessions_expires ON {SESSION_TABLE}(expires_at)")
    except:
        pass
    conn.commit()
    conn.close()


def create_session(data: Dict[str, Any] = None) -> str:
    session_id = secrets.token_urlsafe(32)
    now = time.time()
    expires_at = now + SESSION_MAX_AGE
    data_json = json.dumps(data or {}, ensure_ascii=False)
    conn = _get_system_conn()
    cursor = conn.cursor()
    cursor.execute(f"""
    INSERT INTO {SESSION_TABLE} (session_id, data, created_at, expires_at)
    VALUES (?, ?, ?, ?)
    """, (session_id, data_json, now, expires_at))
    conn.commit()
    conn.close()
    return session_id


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    now = time.time()
    conn = _get_system_conn()
    cursor = conn.cursor()
    cursor.execute(f"""
    SELECT data, created_at FROM {SESSION_TABLE}
    WHERE session_id = ? AND expires_at > ? AND created_at > ?
    """, (session_id, now, now - SESSION_ABSOLUTE_MAX_AGE))
    row = cursor.fetchone()
    conn.close()
    if row and row["data"]:
        try:
            return json.loads(row["data"])
        except:
            return {}
    return None


def update_session(session_id: str, data: Dict[str, Any]) -> bool:
    data_json = json.dumps(data, ensure_ascii=False)
    conn = _get_system_conn()
    cursor = conn.cursor()
    cursor.execute(f"""
    UPDATE {SESSION_TABLE} SET data = ? WHERE session_id = ?
    """, (data_json, session_id))
    conn.commit()
    conn.close()
    return True


def delete_session(session_id: str):
    conn = _get_system_conn()
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM {SESSION_TABLE} WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()


def cleanup_expired_sessions():
    now = time.time()
    conn = _get_system_conn()
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM {SESSION_TABLE} WHERE expires_at < ?", (now,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted


class SessionDict:
    def __init__(self, session_id: str, data: Dict[str, Any], manager: 'SessionManager'):
        self._session_id = session_id
        self._data = data
        self._manager = manager
        self._modified = False

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any):
        self._data[key] = value
        self._modified = True
        self._manager.mark_modified(self._session_id, self._data)

    def __delitem__(self, key: str):
        if key in self._data:
            del self._data[key]
            self._modified = True
            self._manager.mark_modified(self._session_id, self._data)

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def pop(self, key: str, default: Any = None) -> Any:
        if key in self._data:
            value = self._data.pop(key)
            self._modified = True
            self._manager.mark_modified(self._session_id, self._data)
            return value
        return default

    def clear(self):
        self._data.clear()
        self._modified = True
        self._manager.mark_modified(self._session_id, self._data)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()


class SessionManager:
    def __init__(self):
        self._modified_sessions: Dict[str, Dict[str, Any]] = {}
        self._initialized = False

    def _ensure_init(self):
        if not self._initialized:
            init_session_table()
            self._initialized = True

    def mark_modified(self, session_id: str, data: Dict[str, Any]):
        self._modified_sessions[session_id] = data

    def get_or_create_session(self, session_id: Optional[str]) -> SessionDict:
        self._ensure_init()
        if session_id:
            data = get_session(session_id)
            if data is not None:
                return SessionDict(session_id, data, self)
        new_session_id = create_session({})
        return SessionDict(new_session_id, {}, self)

    def save_modified(self):
        for session_id, data in self._modified_sessions.items():
            update_session(session_id, data)
        self._modified_sessions.clear()

    def delete_session(self, session_id: str):
        delete_session(session_id)
        self._modified_sessions.pop(session_id, None)


session_manager = SessionManager()
