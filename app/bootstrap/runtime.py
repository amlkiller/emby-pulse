import os
import sqlite3
import threading

from app.infra.db.session_dao import clear_sessions_if_table_exists
from app.core.config import CONFIG_DIR, FONT_DIR

_original_connect = sqlite3.connect
_patched = False
_weather_cache_preload_thread = None
_weather_cache_preload_stop_event = threading.Event()


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
    global _weather_cache_preload_thread
    if _weather_cache_preload_thread and _weather_cache_preload_thread.is_alive():
        return

    _weather_cache_preload_stop_event.clear()

    def _start_weather_service():
        if _weather_cache_preload_stop_event.wait(10):
            return
        from app.domains.system.system_tools import start_weather_cache_refresh

        start_weather_cache_refresh()

    _weather_cache_preload_thread = threading.Thread(
        target=_start_weather_service,
        daemon=True,
        name="weather-cache-preload",
    )
    _weather_cache_preload_thread.start()


def stop_weather_cache_preload() -> None:
    """Stop delayed weather preload and the refresh loop it may have started."""
    global _weather_cache_preload_thread
    _weather_cache_preload_stop_event.set()
    thread = _weather_cache_preload_thread
    if thread and thread.is_alive():
        thread.join(timeout=1)
    if not thread or not thread.is_alive():
        _weather_cache_preload_thread = None
    try:
        from app.domains.system.system_tools import stop_weather_cache_refresh

        stop_weather_cache_refresh()
    except Exception as e:
        print(f"⚠️ [天气缓存] 停止后台刷新失败（忽略）: {e}")
