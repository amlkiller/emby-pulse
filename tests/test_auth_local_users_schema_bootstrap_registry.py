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


def test_local_users_bootstrap_creates_registry_table(monkeypatch, tmp_path):
    from app.domains.users import auth_dao
    from app.infra.db.schema_registry import TABLE_SCHEMAS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    auth_dao.ensure_local_users_table()
    auth_dao.ensure_local_users_table()

    with sqlite3.connect(db_path) as conn:
        columns = _columns(conn, "local_users")

    assert "local_users" in TABLE_SCHEMAS
    assert {
        "id",
        "username",
        "password_hash",
        "role",
        "remark",
        "avatar",
        "is_enabled",
        "permissions",
        "created_at",
        "updated_at",
        "last_login_at",
        "last_login_ip",
        "totp_secret",
        "totp_enabled",
        "totp_pending_secret",
    }.issubset(columns)


def test_local_users_bootstrap_applies_safe_registered_alters(monkeypatch, tmp_path):
    from app.domains.users import auth_dao
    from app.infra.db.schema_registry import TABLE_ALTERS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE local_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        conn.execute(
            "INSERT INTO local_users (username, password_hash) VALUES (?, ?)",
            ("admin", "hash-a"),
        )
        conn.commit()

    auth_dao.ensure_local_users_table()
    auth_dao.ensure_local_users_table()

    with sqlite3.connect(db_path) as conn:
        columns = _columns(conn, "local_users")
        row = conn.execute(
            """
            SELECT username, password_hash, role, remark, avatar, is_enabled, permissions,
                   last_login_at, last_login_ip, totp_secret, totp_enabled, totp_pending_secret
            FROM local_users
            """
        ).fetchone()

    assert TABLE_ALTERS["local_users"] == [
        "ALTER TABLE local_users ADD COLUMN role TEXT DEFAULT 'admin'",
        "ALTER TABLE local_users ADD COLUMN remark TEXT DEFAULT ''",
        "ALTER TABLE local_users ADD COLUMN avatar TEXT DEFAULT ''",
        "ALTER TABLE local_users ADD COLUMN is_enabled INTEGER DEFAULT 1",
        "ALTER TABLE local_users ADD COLUMN permissions TEXT DEFAULT '[]'",
        "ALTER TABLE local_users ADD COLUMN last_login_at DATETIME",
        "ALTER TABLE local_users ADD COLUMN last_login_ip TEXT",
        "ALTER TABLE local_users ADD COLUMN totp_secret TEXT DEFAULT ''",
        "ALTER TABLE local_users ADD COLUMN totp_enabled INTEGER DEFAULT 0",
        "ALTER TABLE local_users ADD COLUMN totp_pending_secret TEXT DEFAULT ''",
    ]
    registered_alters = "\n".join(TABLE_ALTERS["local_users"])
    assert "ADD COLUMN username TEXT UNIQUE NOT NULL" not in registered_alters
    assert "ADD COLUMN password_hash TEXT NOT NULL" not in registered_alters
    assert "ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP" not in registered_alters
    assert "ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP" not in registered_alters
    for alter_sql in TABLE_ALTERS["local_users"]:
        column_name = alter_sql.split("ADD COLUMN ", 1)[1].split(" ", 1)[0]
        assert column_name in columns
    assert row == ("admin", "hash-a", "admin", "", "", 1, "[]", None, None, "", 0, "")


def test_local_users_totp_dao_paths_work_after_registry_bootstrap(monkeypatch, tmp_path):
    from app.domains.users import auth_dao

    _use_temp_system_db(monkeypatch, tmp_path)
    auth_dao.ensure_local_users_table()
    auth_dao.create_local_user("admin", "hash-a", "admin", "Admin", "[]")

    row = auth_dao.get_local_user_id_by_username("admin")
    user_id = row["id"]

    auth_dao.set_local_user_totp_pending_secret(user_id, "pending-secret")
    pending = auth_dao.get_local_user_totp_pending_secret(user_id)
    assert pending["totp_pending_secret"] == "pending-secret"

    auth_dao.enable_local_user_totp(user_id, "enabled-secret")
    login_user = auth_dao.get_local_user_for_login("admin")
    assert login_user["totp_secret"] == "enabled-secret"
    assert login_user["totp_enabled"] == 1
    assert auth_dao.get_local_user_totp_setup_secret(user_id)["totp_pending_secret"] == ""

    auth_dao.disable_local_user_totp(user_id)
    assert auth_dao.get_local_user_totp_secret(user_id)["totp_secret"] == ""
    assert auth_dao.get_local_user_totp_enabled(user_id)["totp_enabled"] == 0


def test_local_users_bootstrap_uses_schema_registry_instead_of_local_ddl():
    source = (_REPO_ROOT / "app/domains/users/auth_dao.py").read_text(encoding="utf-8")

    assert "from app.infra.db.schema_bootstrap import ensure_registered_table" in source
    assert "from app.infra.db.schema_registry import TABLE_ALTERS, TABLE_SCHEMAS" not in source
    assert 'ensure_registered_table(cursor, "local_users")' in source
    assert "TABLE_SCHEMAS[" not in source
    assert "TABLE_ALTERS.get" not in source
    assert "CREATE TABLE IF NOT EXISTS local_users" not in source
    assert "ALTER TABLE local_users ADD COLUMN" not in source

    for unsafe_alter in (
        "ALTER TABLE local_users ADD COLUMN username TEXT UNIQUE NOT NULL",
        "ALTER TABLE local_users ADD COLUMN password_hash TEXT NOT NULL",
        "ALTER TABLE local_users ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE local_users ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP",
    ):
        assert unsafe_alter not in source
