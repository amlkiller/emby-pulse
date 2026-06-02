import inspect
import sqlite3
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _use_temp_system_db(monkeypatch, tmp_path):
    from app.infra.db.system_store import system_store

    db_path = tmp_path / "system_store.db"
    monkeypatch.setattr(system_store, "db_path", str(db_path))
    return db_path


def _columns(conn, table_name):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def test_plugin_tables_bootstrap_uses_schema_registry_and_preserves_index(monkeypatch, tmp_path):
    from app.infra.db.schema_registry import TABLE_SCHEMAS
    from app.plugins import plugin_dao

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    plugin_dao.ensure_plugin_tables()
    plugin_dao.ensure_plugin_tables()

    with sqlite3.connect(db_path) as conn:
        plugin_state_columns = _columns(conn, "plugin_state")
        plugin_log_columns = _columns(conn, "plugin_logs")
        indexes = {
            row[1]
            for row in conn.execute(
                "SELECT type, name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }

    assert "plugin_state" in TABLE_SCHEMAS
    assert "plugin_logs" in TABLE_SCHEMAS
    assert {"plugin_id", "enabled", "config"}.issubset(plugin_state_columns)
    assert {"id", "plugin_id", "level", "message", "created_at"}.issubset(plugin_log_columns)
    assert "idx_plugin_logs_plugin_id" in indexes


def test_plugin_dao_smoke_paths_work_after_registry_bootstrap(monkeypatch, tmp_path):
    from app.plugins import plugin_dao

    _use_temp_system_db(monkeypatch, tmp_path)
    plugin_dao.ensure_plugin_tables()

    plugin_dao.set_plugin_enabled("sample", True)
    plugin_dao.save_plugin_config("sample", {"enabled": True, "limit": 3})
    plugin_dao.add_plugin_log("sample", "info", "started")

    states = plugin_dao.list_plugin_states()
    logs = plugin_dao.list_plugin_logs("sample")

    assert states[0]["plugin_id"] == "sample"
    assert states[0]["enabled"] == 1
    assert plugin_dao.get_plugin_config("sample") == {"enabled": True, "limit": 3}
    assert logs[0]["level"] == "info"
    assert logs[0]["message"] == "started"

    plugin_dao.clear_plugin_logs("sample")
    assert plugin_dao.list_plugin_logs("sample") == []


def test_keep_alive_bootstrap_creates_registry_table_and_applies_alters(monkeypatch, tmp_path):
    from app.infra.db.schema_registry import TABLE_ALTERS, TABLE_SCHEMAS
    from app.plugins.keep_alive import keep_alive_dao

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE keep_alive_violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                user_name TEXT NOT NULL,
                year_month TEXT NOT NULL,
                hours REAL DEFAULT 0,
                days INTEGER DEFAULT 0,
                min_hours REAL DEFAULT 0,
                min_days INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, year_month)
            )
            """
        )
        conn.commit()

    keep_alive_dao.ensure_keep_alive_violations_table()
    keep_alive_dao.ensure_keep_alive_violations_table()

    with sqlite3.connect(db_path) as conn:
        columns = _columns(conn, "keep_alive_violations")

    assert "keep_alive_violations" in TABLE_SCHEMAS
    assert TABLE_ALTERS["keep_alive_violations"] == [
        "ALTER TABLE keep_alive_violations ADD COLUMN action TEXT DEFAULT 'warn'",
        "ALTER TABLE keep_alive_violations ADD COLUMN disabled INTEGER DEFAULT 0",
    ]
    assert {"action", "disabled"}.issubset(columns)


def test_keep_alive_dao_smoke_paths_work_after_registry_bootstrap(monkeypatch, tmp_path):
    from app.plugins.keep_alive import keep_alive_dao

    _use_temp_system_db(monkeypatch, tmp_path)
    keep_alive_dao.ensure_keep_alive_violations_table()

    keep_alive_dao.save_keep_alive_violation(
        user_id="u1",
        user_name="User One",
        year_month="2026-06",
        hours=1.5,
        days=2,
        min_hours=10,
        min_days=5,
        action="disable",
        disabled=True,
    )

    rows = keep_alive_dao.list_keep_alive_violations("2026-06", limit=10, offset=0)

    assert keep_alive_dao.list_keep_alive_months()[0]["year_month"] == "2026-06"
    assert keep_alive_dao.count_keep_alive_violations("2026-06") == 1
    assert keep_alive_dao.count_keep_alive_disabled() == 1
    assert keep_alive_dao.count_keep_alive_unique_users() == 1
    assert rows[0]["action"] == "disable"
    assert rows[0]["disabled"] == 1

    keep_alive_dao.update_keep_alive_violation_disabled(rows[0]["id"], False)
    assert keep_alive_dao.count_keep_alive_disabled() == 0


def test_plugin_bootstraps_do_not_keep_local_registry_owned_ddl():
    from app.plugins import plugin_dao
    from app.plugins.keep_alive import keep_alive_dao

    plugin_source = inspect.getsource(plugin_dao.ensure_plugin_tables)
    keep_alive_source = inspect.getsource(keep_alive_dao.ensure_keep_alive_violations_table)

    assert "ensure_registered_table(cursor, table_name)" in plugin_source
    assert "CREATE TABLE IF NOT EXISTS plugin_state" not in plugin_source
    assert "CREATE TABLE IF NOT EXISTS plugin_logs" not in plugin_source
    assert "CREATE INDEX IF NOT EXISTS idx_plugin_logs_plugin_id" not in plugin_source

    assert 'ensure_registered_table(cursor, "keep_alive_violations")' in keep_alive_source
    assert "CREATE TABLE IF NOT EXISTS keep_alive_violations" not in keep_alive_source
    assert "ALTER TABLE keep_alive_violations ADD COLUMN" not in keep_alive_source
