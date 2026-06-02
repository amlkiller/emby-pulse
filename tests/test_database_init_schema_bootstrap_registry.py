import inspect
import sqlite3
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _columns(conn, table_name):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def test_init_system_db_creates_simple_tables_from_schema_registry(monkeypatch, tmp_path):
    from app.infra.db import database
    from app.infra.db.schema_registry import SYSTEM_TABLES, TABLE_SCHEMAS

    db_path = tmp_path / "system_store.db"
    monkeypatch.setattr(database, "SYSTEM_DB_PATH", str(db_path))

    database.init_system_db()
    database.init_system_db()

    with sqlite3.connect(db_path) as conn:
        existing_tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }

        for table_name in database._REGISTRY_SYSTEM_INIT_TABLES:
            assert table_name in SYSTEM_TABLES
            assert table_name in TABLE_SCHEMAS
            assert table_name in existing_tables

        assert {"template_user_id", "route_mode", "req_free", "req_free_count"}.issubset(
            _columns(conn, "invitations")
        )
        assert "is_cleared" in _columns(conn, "sys_notifications")
        assert {"init_password", "tg_username", "tg_display_name"}.issubset(
            _columns(conn, "tg_user_bindings")
        )
        assert {"totp_secret", "totp_enabled", "totp_pending_secret"}.issubset(
            _columns(conn, "local_users")
        )
        assert {"action", "disabled"}.issubset(_columns(conn, "keep_alive_violations"))

        indexes = {
            row[1]
            for row in conn.execute(
                "SELECT type, name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
        assert "idx_point_logs_user" in indexes
        assert "idx_msg_conversations_user" in indexes


def test_init_db_creates_compat_point_core_tables_from_schema_registry(monkeypatch, tmp_path):
    from app.infra.db import database
    from app.infra.db.schema_registry import SYSTEM_TABLES, TABLE_SCHEMAS

    system_db_path = tmp_path / "system_store.db"
    compat_db_path = tmp_path / "playback_reporting.db"
    monkeypatch.setattr(database, "SYSTEM_DB_PATH", str(system_db_path))
    monkeypatch.setattr(database, "DB_PATH", str(compat_db_path))

    database.init_db(skip_migration=True)
    database.init_db(skip_migration=True)

    with sqlite3.connect(compat_db_path) as conn:
        existing_tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }

        for table_name in database._REGISTRY_COMPAT_INIT_TABLES:
            assert table_name in SYSTEM_TABLES
            assert table_name in TABLE_SCHEMAS
            assert table_name in existing_tables

        assert {
            "id",
            "user_id",
            "username",
            "action",
            "amount",
            "balance",
            "created_at",
        }.issubset(_columns(conn, "point_logs"))
        assert {"key", "value"}.issubset(_columns(conn, "point_config"))

    with sqlite3.connect(system_db_path) as conn:
        existing_tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }

        for table_name in database._REGISTRY_MESSAGE_INIT_TABLES:
            assert table_name in SYSTEM_TABLES
            assert table_name in TABLE_SCHEMAS
            assert table_name in existing_tables

        assert {
            "id",
            "user_id",
            "username",
            "user_avatar",
            "last_message",
            "last_time",
            "unread_admin",
            "unread_user",
            "created_at",
        }.issubset(_columns(conn, "msg_conversations"))
        assert {
            "id",
            "conversation_id",
            "sender_type",
            "sender_id",
            "sender_name",
            "content",
            "created_at",
        }.issubset(_columns(conn, "msg_items"))
        assert {"id", "user_id", "created_at"}.issubset(_columns(conn, "msg_notify_block"))


def test_database_system_init_uses_registry_for_selected_simple_tables():
    from app.infra.db import database

    source = inspect.getsource(database._create_system_tables)

    assert "for table_name in _REGISTRY_SYSTEM_INIT_TABLES:" in source
    assert "ensure_registered_table(c, table_name)" in source

    for table_name in database._REGISTRY_SYSTEM_INIT_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" not in source

    assert "CREATE TABLE IF NOT EXISTS media_requests" in source
    assert "CREATE TABLE IF NOT EXISTS login_failures" in source
    assert "CREATE TABLE IF NOT EXISTS api_tokens" in source


def test_database_compat_init_uses_registry_for_point_core_tables():
    from app.infra.db import database

    source = inspect.getsource(database.init_db)

    assert "for table_name in _REGISTRY_COMPAT_INIT_TABLES:" in source
    assert "ensure_registered_table(c, table_name)" in source

    for table_name in database._REGISTRY_COMPAT_INIT_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" not in source

    assert "CREATE TABLE IF NOT EXISTS media_requests" in source
    assert "CREATE TABLE IF NOT EXISTS request_users" in source


def test_database_message_init_uses_registry_for_message_tables():
    from app.infra.db import database

    source = inspect.getsource(database.init_db)

    assert "for table_name in _REGISTRY_MESSAGE_INIT_TABLES:" in source
    assert "ensure_registered_table(c, table_name)" in source

    for table_name in database._REGISTRY_MESSAGE_INIT_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" not in source

    assert "CREATE TABLE IF NOT EXISTS media_requests" in source
    assert "CREATE TABLE IF NOT EXISTS request_users" in source
