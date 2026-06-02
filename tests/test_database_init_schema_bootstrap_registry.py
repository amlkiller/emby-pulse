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
        assert {
            "id",
            "lock_key",
            "lock_type",
            "failure_count",
            "locked_until",
            "created_at",
            "updated_at",
        }.issubset(_columns(conn, "login_failures"))
        assert {
            "id",
            "user_id",
            "token",
            "name",
            "expires_at",
            "created_at",
            "last_used_at",
        }.issubset(_columns(conn, "api_tokens"))
        assert {"action", "disabled"}.issubset(_columns(conn, "keep_alive_violations"))
        assert {"user_id", "numbers", "cost", "draw_date", "created_at"}.issubset(
            _columns(conn, "lottery_tickets")
        )
        assert {"draw_date", "winning_numbers", "total_pool", "created_at"}.issubset(
            _columns(conn, "lottery_results")
        )
        assert {"user_id", "ticket_id", "prize_amount", "draw_date"}.issubset(
            _columns(conn, "lottery_winners")
        )
        assert {"total_slots", "filled_slots", "chat_id", "message_id"}.issubset(
            _columns(conn, "scratch_cards")
        )
        assert {"card_id", "slot_number", "prize_amount", "is_scratched"}.issubset(
            _columns(conn, "scratch_card_slots")
        )
        assert {"id", "name", "color", "created_at"}.issubset(_columns(conn, "user_tags"))

        indexes = {
            row[1]
            for row in conn.execute(
                "SELECT type, name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
        assert "idx_point_logs_user" in indexes
        assert "idx_msg_conversations_user" in indexes
        assert "idx_login_failures_key" in indexes
        assert "idx_login_failures_type" in indexes
        assert "idx_login_failures_locked" in indexes
        assert "idx_api_tokens_user" in indexes
        assert "idx_api_tokens_token" in indexes


def test_auth_and_api_token_daos_work_after_registry_system_init(monkeypatch, tmp_path):
    from app.domains.users import auth_dao
    from app.infra.db import api_token_store, database
    from app.infra.db.system_store import system_store

    db_path = tmp_path / "system_store.db"
    monkeypatch.setattr(database, "SYSTEM_DB_PATH", str(db_path))
    monkeypatch.setattr(system_store, "db_path", str(db_path))

    database.init_system_db()

    auth_dao.upsert_login_failure("ip:127.0.0.1", "ip", 2, "2099-01-01 00:00:00")
    login_failure = auth_dao.get_login_failure("ip:127.0.0.1")
    assert login_failure is not None
    assert login_failure["failure_count"] == 2
    assert auth_dao.get_login_failure_count("ip:127.0.0.1") == 2

    auth_dao.upsert_login_failure("ip:expired", "ip", 1, "2000-01-01 00:00:00")
    assert auth_dao.cleanup_expired_login_locks() == 1
    auth_dao.clear_login_failure("ip:127.0.0.1")
    assert auth_dao.get_login_failure_count("ip:127.0.0.1") is None

    system_store.execute(
        "INSERT INTO users_meta (user_id, created_at) VALUES (?, ?)",
        ("user-1", "2026-06-02 00:00:00"),
    )
    api_token_store.create_api_token_record(
        "user-1",
        "token-hash-1",
        "Integration",
        "2099-01-01 00:00:00",
        "2026-06-02 00:00:00",
    )

    tokens = api_token_store.list_api_tokens("user-1")
    assert len(tokens) == 1
    assert tokens[0]["name"] == "Integration"
    assert api_token_store.get_api_token_by_hash("token-hash-1")["expires_at"] == "2099-01-01 00:00:00"

    api_token_store.mark_api_token_used("token-hash-1")
    tokens = api_token_store.list_api_tokens("user-1")
    assert tokens[0]["last_used_at"] is not None

    api_token_store.delete_api_token(tokens[0]["id"], "user-1")
    assert api_token_store.list_api_tokens("user-1") == []


def test_user_tag_daos_work_after_registry_system_init(monkeypatch, tmp_path):
    from app.domains.users import user_dao
    from app.infra.db import database
    from app.infra.db.system_store import system_store

    db_path = tmp_path / "system_store.db"
    monkeypatch.setattr(database, "SYSTEM_DB_PATH", str(db_path))
    monkeypatch.setattr(system_store, "db_path", str(db_path))

    database.init_system_db()

    tag_id = user_dao.create_user_tag("vip", "red")
    rows = user_dao.list_user_tags()
    assert len(rows) == 1
    assert rows[0]["id"] == tag_id
    assert rows[0]["name"] == "vip"
    assert rows[0]["color"] == "red"

    user_dao.save_user_tags("user-a", "vip,trial", "2026-06-02")
    assert user_dao.get_user_tags("user-a") == "vip,trial"

    assert user_dao.delete_user_tag_by_name("vip") is True
    assert user_dao.delete_user_tag_by_name("missing") is False
    assert user_dao.list_user_tags() == []
    assert user_dao.get_user_tags("user-a") == "trial"


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

        for table_name in database._REGISTRY_COMPAT_SIMPLE_INIT_TABLES:
            assert table_name in SYSTEM_TABLES
            assert table_name in TABLE_SCHEMAS
            assert table_name in existing_tables

        for table_name in database._REGISTRY_COMPAT_NOTIFICATION_INIT_TABLES:
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
        assert {
            "id",
            "tmdb_id",
            "chat_id",
            "message_id",
            "is_caption",
            "original_text",
            "created_at",
            "updated_at",
        }.issubset(_columns(conn, "request_admin_messages"))
        assert {"plugin_id", "enabled", "config"}.issubset(_columns(conn, "plugin_state"))
        assert {"id", "layout_json"}.issubset(_columns(conn, "sys_dashboard"))
        assert {"id", "type", "title", "message", "is_read", "is_cleared"}.issubset(
            _columns(conn, "sys_notifications")
        )

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
    assert "CREATE TABLE IF NOT EXISTS login_failures" not in source
    assert "CREATE TABLE IF NOT EXISTS api_tokens" not in source
    assert "CREATE TABLE IF NOT EXISTS user_tags" not in source
    assert "ALTER TABLE scratch_cards ADD COLUMN" not in source


def test_database_compat_init_uses_registry_for_point_core_tables():
    from app.infra.db import database

    source = inspect.getsource(database.init_db)

    assert "for table_name in _REGISTRY_COMPAT_INIT_TABLES:" in source
    assert "ensure_registered_table(c, table_name)" in source

    for table_name in database._REGISTRY_COMPAT_INIT_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" not in source

    assert "CREATE TABLE IF NOT EXISTS media_requests" in source


def test_database_compat_init_uses_registry_for_simple_tables():
    from app.infra.db import database

    source = inspect.getsource(database.init_db)

    assert "for table_name in _REGISTRY_COMPAT_SIMPLE_INIT_TABLES:" in source
    assert "ensure_registered_table(c, table_name)" in source

    for table_name in database._REGISTRY_COMPAT_SIMPLE_INIT_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" not in source

    assert "CREATE TABLE IF NOT EXISTS invitations" in source
    assert "CREATE TABLE IF NOT EXISTS sys_license" in source
    assert "CREATE TABLE IF NOT EXISTS media_requests" in source
    assert "CREATE TABLE IF NOT EXISTS tg_user_bindings" in source


def test_database_compat_init_uses_registry_for_notification_tables():
    from app.infra.db import database

    source = inspect.getsource(database.init_db)

    assert "for table_name in _REGISTRY_COMPAT_NOTIFICATION_INIT_TABLES:" in source
    assert "ensure_registered_table(c, table_name)" in source

    for table_name in database._REGISTRY_COMPAT_NOTIFICATION_INIT_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" not in source

    assert "CREATE TABLE IF NOT EXISTS invitations" in source
    assert "CREATE TABLE IF NOT EXISTS sys_license" in source
    assert "CREATE TABLE IF NOT EXISTS media_requests" in source
    assert "CREATE TABLE IF NOT EXISTS tg_user_bindings" in source


def test_database_message_init_uses_registry_for_message_tables():
    from app.infra.db import database

    source = inspect.getsource(database.init_db)

    assert "for table_name in _REGISTRY_MESSAGE_INIT_TABLES:" in source
    assert "ensure_registered_table(c, table_name)" in source

    for table_name in database._REGISTRY_MESSAGE_INIT_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" not in source

    assert "CREATE TABLE IF NOT EXISTS media_requests" in source
