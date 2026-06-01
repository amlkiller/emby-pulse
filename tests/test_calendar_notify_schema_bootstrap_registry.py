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


def test_calendar_notify_bootstrap_creates_registry_table_and_default_row(monkeypatch, tmp_path):
    from app.domains.notifications import calendar_notify_dao
    from app.infra.db.schema_registry import SYSTEM_TABLES, TABLE_SCHEMAS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    calendar_notify_dao.ensure_calendar_notify_config_table()
    calendar_notify_dao.ensure_calendar_notify_config_table()

    with sqlite3.connect(db_path) as conn:
        columns = _columns(conn, "calendar_notify_config")
        rows = conn.execute(
            """
            SELECT id, enabled, notify_time, channels, tg_chat_id, wecom_touser, last_sent
            FROM calendar_notify_config
            """
        ).fetchall()

    assert "calendar_notify_config" in SYSTEM_TABLES
    assert "calendar_notify_config" in TABLE_SCHEMAS
    assert {
        "id",
        "enabled",
        "notify_time",
        "channels",
        "tg_chat_id",
        "wecom_touser",
        "last_sent",
        "created_at",
        "updated_at",
    }.issubset(columns)
    assert rows == [(1, 0, "09:00", '["tg_bot"]', None, "@all", None)]


def test_calendar_notify_dao_paths_work_after_registry_bootstrap(monkeypatch, tmp_path):
    from app.domains.notifications import calendar_notify_dao

    _use_temp_system_db(monkeypatch, tmp_path)

    calendar_notify_dao.ensure_calendar_notify_config_table()
    calendar_notify_dao.save_calendar_notify_config(
        enabled=True,
        notify_time="18:30",
        channels='["tg_bot","wecom"]',
        tg_chat_id="12345",
        wecom_touser="admin",
    )
    calendar_notify_dao.mark_calendar_notify_sent()

    row = calendar_notify_dao.get_calendar_notify_config()

    assert row["enabled"] == 1
    assert row["notify_time"] == "18:30"
    assert row["channels"] == '["tg_bot","wecom"]'
    assert row["tg_chat_id"] == "12345"
    assert row["wecom_touser"] == "admin"
    assert row["last_sent"]


def test_calendar_notify_bootstrap_uses_schema_registry_instead_of_local_ddl():
    source = (_REPO_ROOT / "app/domains/notifications/calendar_notify_dao.py").read_text(encoding="utf-8")

    assert "from app.infra.db.schema_bootstrap import ensure_registered_table" in source
    assert 'ensure_registered_table(cursor, "calendar_notify_config")' in source
    assert "CREATE TABLE IF NOT EXISTS calendar_notify_config" not in source
