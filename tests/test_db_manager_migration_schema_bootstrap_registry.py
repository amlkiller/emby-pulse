import inspect
import sqlite3
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _columns(conn, table_name):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _indexes(conn, table_name):
    return {row[1] for row in conn.execute(f"PRAGMA index_list({table_name})").fetchall()}


def test_migrate_tables_applies_registered_alters_to_destination(monkeypatch, tmp_path):
    from app.infra.db import db_manager

    old_db_path = tmp_path / "old.db"
    system_db_path = tmp_path / "system.db"
    monkeypatch.setattr(db_manager, "DB_PATH", str(old_db_path))
    monkeypatch.setattr(db_manager, "SYSTEM_DB_PATH", str(system_db_path))

    with sqlite3.connect(old_db_path) as conn:
        conn.execute(
            """
            CREATE TABLE sys_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT,
                title TEXT,
                message TEXT,
                is_read INTEGER DEFAULT 0,
                action_url TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            INSERT INTO sys_notifications (type, title, message, is_read, action_url)
            VALUES ('system', 'Migration', 'registered alter check', 0, '/system')
            """
        )
        conn.commit()

    result = db_manager.migrate_tables(tables=["sys_notifications"])

    assert result["success"] is True
    assert result["migrated_tables"]["sys_notifications"]["migrated"] == 1
    with sqlite3.connect(system_db_path) as conn:
        assert "is_cleared" in _columns(conn, "sys_notifications")
        migrated_row = conn.execute(
            "SELECT title, is_cleared FROM sys_notifications WHERE type = ?",
            ("system",),
        ).fetchone()
        assert migrated_row == ("Migration", 0)


def test_migrate_tables_applies_registered_indexes_to_destination(monkeypatch, tmp_path):
    from app.infra.db import db_manager

    old_db_path = tmp_path / "old.db"
    system_db_path = tmp_path / "system.db"
    monkeypatch.setattr(db_manager, "DB_PATH", str(old_db_path))
    monkeypatch.setattr(db_manager, "SYSTEM_DB_PATH", str(system_db_path))

    with sqlite3.connect(old_db_path) as conn:
        conn.execute(
            """
            CREATE TABLE login_failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lock_key TEXT NOT NULL UNIQUE,
                lock_type TEXT NOT NULL,
                failure_count INTEGER DEFAULT 0,
                locked_until DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            INSERT INTO login_failures (lock_key, lock_type, failure_count, locked_until)
            VALUES ('ip:127.0.0.1', 'ip', 2, '2099-01-01 00:00:00')
            """
        )
        conn.commit()

    result = db_manager.migrate_tables(tables=["login_failures"])

    assert result["success"] is True
    assert result["migrated_tables"]["login_failures"]["migrated"] == 1
    with sqlite3.connect(system_db_path) as conn:
        assert {
            "idx_login_failures_key",
            "idx_login_failures_type",
            "idx_login_failures_locked",
        }.issubset(_indexes(conn, "login_failures"))


def test_db_manager_migration_uses_schema_bootstrap_for_registry_tables():
    from app.infra.db import db_manager

    source = inspect.getsource(db_manager.migrate_tables)

    assert "ensure_registered_table(new_cursor, table)" in source
    assert "new_cursor.execute(TABLE_SCHEMAS[table])" not in source
