import secrets
import time
import logging
import threading
from typing import Optional, Any, Dict

from app.infra.db.session_dao import (
    cleanup_expired_sessions as dao_cleanup_expired_sessions,
    create_session as dao_create_session,
    delete_session as dao_delete_session,
    ensure_session_table,
    get_session as dao_get_session,
    update_session as dao_update_session,
)

SESSION_TABLE = "sessions"
SESSION_COOKIE_NAME = "session_id"
SESSION_MAX_AGE = 24 * 3600  # 24小时（空闲超时）
SESSION_ABSOLUTE_MAX_AGE = 7 * 24 * 3600  # 7天（绝对超时）
_session_cleanup_started = False
_session_cleanup_lock = threading.Lock()
_session_cleanup_stop_event = threading.Event()
_session_cleanup_thread = None


def create_session(data: Dict[str, Any] = None) -> str:
    session_id = secrets.token_urlsafe(32)
    now = time.time()
    expires_at = now + SESSION_MAX_AGE
    dao_create_session(session_id, data or {}, now, expires_at)
    return session_id


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    now = time.time()
    row = dao_get_session(session_id, now, now - SESSION_ABSOLUTE_MAX_AGE)
    if row and row["data"]:
        try:
            import json

            return json.loads(row["data"])
        except:
            return {}
    return None


def update_session(session_id: str, data: Dict[str, Any]) -> bool:
    dao_update_session(session_id, data)
    return True


def cleanup_expired_sessions():
    now = time.time()
    return dao_cleanup_expired_sessions(now)


def start_session_cleanup_loop(interval_seconds: int = 3600) -> None:
    global _session_cleanup_started, _session_cleanup_thread
    with _session_cleanup_lock:
        if _session_cleanup_started:
            return
        _session_cleanup_started = True
        _session_cleanup_stop_event.clear()

    try:
        deleted = cleanup_expired_sessions()
        if deleted > 0:
            print(f"[Session] 已清理 {deleted} 个过期会话")
    except Exception as e:
        print(f"[Session] 清理失败: {e}")

    def _session_cleanup_loop():
        logger = logging.getLogger("uvicorn")
        while not _session_cleanup_stop_event.wait(interval_seconds):
            try:
                deleted = cleanup_expired_sessions()
                if deleted > 0:
                    logger.info(f"[Session] 已清理 {deleted} 个过期会话")
            except Exception as e:
                logger.error(f"[Session] 清理失败: {e}")

    _session_cleanup_thread = threading.Thread(target=_session_cleanup_loop, daemon=True, name="session-cleanup")
    _session_cleanup_thread.start()


def stop_session_cleanup_loop() -> None:
    global _session_cleanup_started, _session_cleanup_thread
    with _session_cleanup_lock:
        if not _session_cleanup_started:
            return
        _session_cleanup_stop_event.set()
        thread = _session_cleanup_thread
        _session_cleanup_started = False
        _session_cleanup_thread = None
    if thread and thread.is_alive():
        thread.join(timeout=1)


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
        """销毁当前 session 行并切换到全新的空 session_id。

        登录成功时调用可防止 Session Fixation；登出时调用可避免数据库残留旧空行。
        返回后对 self 的写入会落到新的 session_id 上。
        """
        old_id = self._session_id
        # 先从待保存队列里把旧 id 摘掉，否则随后 save_modified 会把空数据回写到旧行
        self._manager.discard_pending(old_id)
        dao_delete_session(old_id)
        new_id = create_session({})
        self._session_id = new_id
        self._data = {}
        self._modified = True
        # 不再 mark_modified：新行已经在 DB 中以空数据存在，
        # 后续 __setitem__ 会按新 id 再排进 _modified_sessions。

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
            ensure_session_table()
            self._initialized = True

    def initialize(self):
        self._ensure_init()

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
        items = list(self._modified_sessions.items())
        self._modified_sessions.clear()
        for session_id, data in items:
            update_session(session_id, data)

    def delete_session(self, session_id: str):
        dao_delete_session(session_id)
        self._modified_sessions.pop(session_id, None)

    def discard_pending(self, session_id: str):
        """从待保存队列里移除指定 session_id，避免回写已删除的 session 行。"""
        self._modified_sessions.pop(session_id, None)


session_manager = SessionManager()


def start_session_services() -> None:
    session_manager.initialize()
    start_session_cleanup_loop()
