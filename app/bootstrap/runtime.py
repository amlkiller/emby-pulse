import os
import sqlite3
import threading
import time

from app.dao.session_dao import clear_sessions_if_table_exists
from app.core.config import CONFIG_DIR, FONT_DIR

_original_connect = sqlite3.connect
_patched = False


def patch_sqlite_connect() -> None:
    """Apply the project-wide SQLite connection patch once."""
    global _patched
    if _patched:
        return

    def _patched_connect(database, timeout=5.0, *args, **kwargs):
        if timeout == 5.0:
            timeout = 30.0
        conn = _original_connect(database, timeout=timeout, *args, **kwargs)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            pass
        return conn

    sqlite3.connect = _patched_connect
    _patched = True


def ensure_runtime_directories() -> None:
    """Create directories required by the application at startup."""
    for path in ("static", "templates", CONFIG_DIR, FONT_DIR):
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)


def clear_system_sessions() -> None:
    """Clear persisted sessions on startup to force a clean login."""
    try:
        deleted_count = clear_sessions_if_table_exists()
        if deleted_count is not None:
            print(f"🔒 [安全] 已清空 {deleted_count} 个 Session，所有用户需要重新登录")
        else:
            print("🔒 [安全] Session 表不存在，跳过清理")
    except Exception as e:
        print(f"⚠️ [安全] 清空 Session 失败: {e}")


def start_weather_cache_preload() -> None:
    """Preload weather cache in the background after startup."""
    def _start_weather_service():
        time.sleep(10)
        from app.domains.system.system_tools import preload_weather_cache

        preload_weather_cache()

    threading.Thread(target=_start_weather_service, daemon=True).start()
