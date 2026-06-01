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


def test_notifications_bootstrap_uses_schema_registry(monkeypatch, tmp_path):
    from app.infra.db import notification_dao
    from app.infra.db.schema_registry import TABLE_ALTERS, TABLE_SCHEMAS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    notification_dao.ensure_notifications_table()
    notification_dao.ensure_notifications_table()

    with sqlite3.connect(db_path) as conn:
        columns = _columns(conn, "sys_notifications")

    assert "sys_notifications" in TABLE_SCHEMAS
    assert TABLE_ALTERS["sys_notifications"] == [
        "ALTER TABLE sys_notifications ADD COLUMN is_cleared INTEGER DEFAULT 0"
    ]
    assert {"id", "type", "title", "message", "is_read", "action_url", "created_at", "is_cleared"}.issubset(
        columns
    )


def test_notifications_bootstrap_upgrades_existing_table(monkeypatch, tmp_path):
    from app.infra.db import notification_dao
    from app.infra.db.schema_registry import TABLE_SCHEMAS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(TABLE_SCHEMAS["sys_notifications"])
        conn.commit()

    notification_dao.ensure_notifications_table()

    with sqlite3.connect(db_path) as conn:
        assert "is_cleared" in _columns(conn, "sys_notifications")


def test_dashboard_helpers_use_schema_registry_and_preserve_layout(monkeypatch, tmp_path):
    from app.domains.system import system_tool_dao

    db_path = _use_temp_system_db(monkeypatch, tmp_path)
    layout = {
        "cards": [
            {"id": "server", "visible": True},
            {"id": "activity", "visible": False},
        ]
    }

    assert system_tool_dao.get_dashboard_layout() is None

    system_tool_dao.save_dashboard_layout(layout)

    with sqlite3.connect(db_path) as conn:
        columns = _columns(conn, "sys_dashboard")

    assert {"id", "layout_json"}.issubset(columns)
    assert system_tool_dao.get_dashboard_layout() == layout


def test_small_bootstrap_helpers_do_not_keep_local_registry_owned_ddl():
    notification_source = (_REPO_ROOT / "app/infra/db/notification_dao.py").read_text(encoding="utf-8")
    system_tool_source = (_REPO_ROOT / "app/domains/system/system_tool_dao.py").read_text(encoding="utf-8")

    assert "TABLE_SCHEMAS[\"sys_notifications\"]" in notification_source
    assert "TABLE_ALTERS[\"sys_notifications\"]" in notification_source
    assert "CREATE TABLE IF NOT EXISTS sys_notifications" not in notification_source
    assert "ALTER TABLE sys_notifications ADD COLUMN is_cleared" not in notification_source

    assert "TABLE_SCHEMAS[\"sys_dashboard\"]" in system_tool_source
    assert "CREATE TABLE IF NOT EXISTS sys_dashboard" not in system_tool_source
