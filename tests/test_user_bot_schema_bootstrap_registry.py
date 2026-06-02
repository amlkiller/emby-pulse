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


def test_user_bot_bootstrap_creates_registry_tables(monkeypatch, tmp_path):
    from app.domains.users import user_bot_dao
    from app.infra.db.schema_registry import SYSTEM_TABLES, TABLE_SCHEMAS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    user_bot_dao.ensure_user_bot_tables()
    user_bot_dao.ensure_user_bot_tables()

    with sqlite3.connect(db_path) as conn:
        existing_tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert set(user_bot_dao.USER_BOT_REGISTRY_TABLES).issubset(existing_tables)
        assert {
            "tg_user_id",
            "tg_username",
            "tg_display_name",
            "emby_user_id",
            "emby_username",
            "init_password",
            "bound_at",
        }.issubset(_columns(conn, "tg_user_bindings"))
        assert {"tg_user_id", "reason", "created_at"}.issubset(_columns(conn, "tg_user_blacklist"))
        assert {"id", "tg_user_id", "emby_username", "emby_user_id", "reg_type", "created_at"}.issubset(
            _columns(conn, "tg_reg_logs")
        )
        assert {"tg_user_id", "tg_name", "first_seen", "last_seen"}.issubset(_columns(conn, "tg_bot_users"))
        assert {"channel_id", "tg_user_id", "channel_title", "bound_at"}.issubset(
            _columns(conn, "tg_channel_bindings")
        )

    for table_name in user_bot_dao.USER_BOT_REGISTRY_TABLES:
        assert table_name in SYSTEM_TABLES
        assert table_name in TABLE_SCHEMAS


def test_user_bot_bootstrap_applies_registered_binding_alters(monkeypatch, tmp_path):
    from app.domains.users import user_bot_dao
    from app.infra.db.schema_registry import TABLE_ALTERS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE tg_user_bindings (
                tg_user_id TEXT PRIMARY KEY,
                emby_user_id TEXT,
                emby_username TEXT,
                bound_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        conn.execute(
            "INSERT INTO tg_user_bindings (tg_user_id, emby_user_id, emby_username) VALUES (?, ?, ?)",
            ("1001", "emby-a", "Alice"),
        )
        conn.commit()

    user_bot_dao.ensure_user_bot_tables()
    user_bot_dao.ensure_user_bot_tables()

    with sqlite3.connect(db_path) as conn:
        columns = _columns(conn, "tg_user_bindings")
        row = conn.execute(
            "SELECT tg_user_id, emby_user_id, emby_username, init_password, tg_username, tg_display_name FROM tg_user_bindings"
        ).fetchone()

    assert TABLE_ALTERS["tg_user_bindings"] == [
        "ALTER TABLE tg_user_bindings ADD COLUMN init_password TEXT DEFAULT ''",
        "ALTER TABLE tg_user_bindings ADD COLUMN tg_username TEXT DEFAULT ''",
        "ALTER TABLE tg_user_bindings ADD COLUMN tg_display_name TEXT DEFAULT ''",
    ]
    for alter_sql in TABLE_ALTERS["tg_user_bindings"]:
        column_name = alter_sql.split("ADD COLUMN ", 1)[1].split(" ", 1)[0]
        assert column_name in columns
    assert row == ("1001", "emby-a", "Alice", "", "", "")


def test_user_bot_binding_queries_work_after_registry_bootstrap(monkeypatch, tmp_path):
    from app.domains.users import user_bot_dao
    from app.infra.db.schema_registry import TABLE_SCHEMAS
    from app.infra.db.system_store import system_store

    _use_temp_system_db(monkeypatch, tmp_path)
    user_bot_dao.ensure_user_bot_tables()
    with system_store.connect() as conn:
        conn.execute(TABLE_SCHEMAS["users_meta"])
        conn.commit()

    user_bot_dao.bind_user(
        "1002",
        "emby-b",
        "Bob",
        init_password="init-pass",
        tg_username="bob_tg",
        tg_display_name="Bob TG",
    )

    assert user_bot_dao.get_binding("1002") == {
        "emby_user_id": "emby-b",
        "emby_username": "Bob",
        "init_password": "init-pass",
        "tg_username": "bob_tg",
        "tg_name": "Bob TG",
    }
    assert user_bot_dao.get_tg_user_id_by_username("bob_tg") == "1002"
    whois_rows = user_bot_dao.search_whois_bindings("bob_tg")
    assert len(whois_rows) == 1
    assert whois_rows[0]["tg_display_name"] == "Bob TG"


def test_user_bot_helper_queries_work_after_registry_bootstrap(monkeypatch, tmp_path):
    from app.domains.users import user_bot_dao

    _use_temp_system_db(monkeypatch, tmp_path)
    user_bot_dao.ensure_user_bot_tables()

    user_bot_dao.record_bot_user("2001", "Bot User")
    assert user_bot_dao.list_bot_users() == [{"tg_user_id": "2001", "tg_name": "Bot User"}]
    assert user_bot_dao.get_bot_user_name("2001") == "Bot User"

    user_bot_dao.bind_channel("channel-1", "2001", "Channel")
    channel_binding = user_bot_dao.get_channel_binding("channel-1")
    assert channel_binding["tg_user_id"] == "2001"
    assert channel_binding["channel_title"] == "Channel"

    user_bot_dao.unbind_channel("channel-1")
    assert user_bot_dao.get_channel_binding("channel-1") is None


def test_user_bot_bootstrap_uses_schema_registry_for_owned_tables():
    source = (_REPO_ROOT / "app/domains/users/user_bot_dao.py").read_text(encoding="utf-8")

    assert "from app.infra.db.schema_bootstrap import ensure_registered_table" in source
    assert "from app.infra.db.schema_registry import TABLE_ALTERS, TABLE_SCHEMAS" not in source
    assert "USER_BOT_REGISTRY_TABLES" in source
    assert "ensure_registered_table(cursor, table_name)" in source
    assert "TABLE_SCHEMAS[table_name]" not in source
    assert "TABLE_ALTERS.get(table_name, [])" not in source

    for registry_owned_table in (
        "tg_user_bindings",
        "tg_user_blacklist",
        "tg_reg_logs",
        "tg_bot_users",
        "tg_channel_bindings",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {registry_owned_table}" not in source
        assert f"CREATE TABLE {registry_owned_table}" not in source

    assert "ALTER TABLE tg_user_bindings ADD COLUMN" not in source
