import json
from datetime import datetime

from app.infra.db.system_store import system_store


def ensure_plugin_tables() -> None:
    with system_store.connect(timeout=10) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plugin_state (
                plugin_id TEXT PRIMARY KEY,
                enabled INTEGER DEFAULT 0,
                config TEXT DEFAULT '{}'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plugin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plugin_id TEXT NOT NULL,
                level TEXT DEFAULT 'info',
                message TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_plugin_logs_plugin_id ON plugin_logs(plugin_id)")
        conn.commit()


def list_plugin_states():
    return system_store.fetch_all("SELECT plugin_id, enabled, config FROM plugin_state")


def set_plugin_enabled(plugin_id: str, enabled: bool) -> None:
    system_store.execute(
        """
        INSERT OR REPLACE INTO plugin_state (plugin_id, enabled, config)
        VALUES (?, ?, COALESCE((SELECT config FROM plugin_state WHERE plugin_id = ?), '{}'))
        """,
        (plugin_id, 1 if enabled else 0, plugin_id),
    )


def get_plugin_config(plugin_id: str) -> dict:
    row = system_store.fetch_one("SELECT config FROM plugin_state WHERE plugin_id = ?", (plugin_id,))
    try:
        return json.loads(row["config"]) if row and row["config"] else {}
    except Exception:
        return {}


def save_plugin_config(plugin_id: str, config: dict) -> None:
    system_store.execute(
        """
        INSERT OR REPLACE INTO plugin_state (plugin_id, enabled, config)
        VALUES (?, COALESCE((SELECT enabled FROM plugin_state WHERE plugin_id = ?), 0), ?)
        """,
        (plugin_id, plugin_id, json.dumps(config, ensure_ascii=False)),
    )


def add_plugin_log(plugin_id: str, level: str, message: str) -> None:
    system_store.execute(
        "INSERT INTO plugin_logs (plugin_id, level, message, created_at) VALUES (?, ?, ?, ?)",
        (plugin_id, level, message, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )


def list_plugin_logs(plugin_id: str, limit: int = 50):
    return system_store.fetch_all(
        """
        SELECT level, message, created_at
        FROM plugin_logs
        WHERE plugin_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (plugin_id, limit),
    )


def clear_plugin_logs(plugin_id: str) -> None:
    system_store.execute("DELETE FROM plugin_logs WHERE plugin_id = ?", (plugin_id,))
