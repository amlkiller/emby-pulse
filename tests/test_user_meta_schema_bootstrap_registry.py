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


def test_users_meta_bootstrap_creates_registry_table(monkeypatch, tmp_path):
    from app.domains.users import user_dao
    from app.infra.db.schema_registry import TABLE_SCHEMAS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    user_dao.ensure_users_meta_schema()
    user_dao.ensure_users_meta_schema()

    with sqlite3.connect(db_path) as conn:
        columns = _columns(conn, "users_meta")

    assert "users_meta" in TABLE_SCHEMAS
    assert {
        "user_id",
        "expire_date",
        "note",
        "created_at",
        "max_concurrent",
        "risk_level",
        "is_vip",
        "points",
        "block_routes",
        "allow_routes",
        "remark",
        "admin_disabled",
        "req_free",
        "req_free_count",
        "tags",
        "emby_pw_hash",
        "admin_enabled_folders",
        "hidden_libraries",
    }.issubset(columns)


def test_users_meta_bootstrap_applies_safe_registered_alters(monkeypatch, tmp_path):
    from app.domains.users import user_dao
    from app.infra.db.schema_registry import TABLE_ALTERS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE users_meta (
                user_id TEXT PRIMARY KEY,
                expire_date TEXT,
                note TEXT,
                created_at TEXT
            )"""
        )
        conn.execute(
            "INSERT INTO users_meta (user_id, expire_date, created_at) VALUES (?, ?, ?)",
            ("user-a", "2099-01-01", "2026-06-02"),
        )
        conn.commit()

    user_dao.ensure_users_meta_schema()
    user_dao.ensure_users_meta_schema()

    with sqlite3.connect(db_path) as conn:
        columns = _columns(conn, "users_meta")
        row = conn.execute(
            """
            SELECT user_id, max_concurrent, risk_level, is_vip, points, block_routes,
                   allow_routes, remark, admin_disabled, req_free, req_free_count,
                   tags, emby_pw_hash, admin_enabled_folders, hidden_libraries
            FROM users_meta
            """
        ).fetchone()

    assert TABLE_ALTERS["users_meta"] == [
        "ALTER TABLE users_meta ADD COLUMN max_concurrent INTEGER",
        "ALTER TABLE users_meta ADD COLUMN risk_level TEXT DEFAULT 'safe'",
        "ALTER TABLE users_meta ADD COLUMN is_vip INTEGER DEFAULT 0",
        "ALTER TABLE users_meta ADD COLUMN points INTEGER DEFAULT 0",
        "ALTER TABLE users_meta ADD COLUMN block_routes TEXT DEFAULT ''",
        "ALTER TABLE users_meta ADD COLUMN allow_routes TEXT DEFAULT ''",
        "ALTER TABLE users_meta ADD COLUMN remark TEXT DEFAULT ''",
        "ALTER TABLE users_meta ADD COLUMN admin_disabled INTEGER DEFAULT 0",
        "ALTER TABLE users_meta ADD COLUMN req_free INTEGER DEFAULT 0",
        "ALTER TABLE users_meta ADD COLUMN req_free_count INTEGER DEFAULT -1",
        "ALTER TABLE users_meta ADD COLUMN tags TEXT DEFAULT ''",
        "ALTER TABLE users_meta ADD COLUMN emby_pw_hash TEXT DEFAULT ''",
        "ALTER TABLE users_meta ADD COLUMN admin_enabled_folders TEXT",
        "ALTER TABLE users_meta ADD COLUMN hidden_libraries TEXT DEFAULT ''",
    ]
    registered_alters = "\n".join(TABLE_ALTERS["users_meta"])
    assert "UNIQUE" not in registered_alters
    assert "NOT NULL" not in registered_alters
    assert "DEFAULT CURRENT_TIMESTAMP" not in registered_alters
    for alter_sql in TABLE_ALTERS["users_meta"]:
        column_name = alter_sql.split("ADD COLUMN ", 1)[1].split(" ", 1)[0]
        assert column_name in columns
    assert row == (
        "user-a",
        None,
        "safe",
        0,
        0,
        "",
        "",
        "",
        0,
        0,
        -1,
        "",
        "",
        None,
        "",
    )


def test_users_meta_admin_disabled_migration_preserves_backfill(monkeypatch, tmp_path):
    from app.domains.users import user_dao

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE users_meta (
                user_id TEXT PRIMARY KEY,
                expire_date TEXT,
                created_at TEXT
            )"""
        )
        conn.executemany(
            "INSERT INTO users_meta (user_id, expire_date, created_at) VALUES (?, ?, ?)",
            [
                ("active-user", "2099-01-01", "2026-06-02"),
                ("expired-user", "2020-01-01", "2026-06-02"),
                ("empty-expire-user", "", "2026-06-02"),
            ],
        )
        conn.commit()

    migrated = user_dao.migrate_admin_disabled(
        ["active-user", "expired-user", "empty-expire-user", "missing-user"],
        "2026-06-02",
    )
    second_run = user_dao.migrate_admin_disabled(["active-user"], "2026-06-02")

    with sqlite3.connect(db_path) as conn:
        rows = dict(conn.execute("SELECT user_id, admin_disabled FROM users_meta").fetchall())

    assert migrated == 3
    assert second_run is None
    assert rows == {
        "active-user": 1,
        "expired-user": 0,
        "empty-expire-user": 1,
    }


def test_users_meta_dao_paths_work_after_registry_bootstrap(monkeypatch, tmp_path):
    from app.domains.users import user_dao

    _use_temp_system_db(monkeypatch, tmp_path)
    user_dao.ensure_users_meta_schema()

    user_dao.save_user_admin_disabled("user-a", True, "2026-06-02")
    user_dao.save_user_req_permission("user-a", 2, 5, "2026-06-02")
    user_dao.save_user_routes_preserve("user-a", "route-a", "route-b", "2026-06-02")
    user_dao.save_user_tags("user-a", "vip,trial", "2026-06-02")
    user_dao.save_user_admin_enabled_folders("user-a", "folder-a,folder-b")
    user_dao.save_user_hidden_libraries("user-a", "folder-b")

    meta = user_dao.get_user_meta("user-a")
    req_permission = user_dao.get_user_req_permission("user-a")
    routes = user_dao.get_user_routes("user-a")
    library_settings = user_dao.get_user_library_settings("user-a")

    assert meta["admin_disabled"] == 1
    assert meta["tags"] == "vip,trial"
    assert req_permission == {"req_free": 2, "req_free_count": 5}
    assert routes["allow_routes"] == "route-a"
    assert routes["block_routes"] == "route-b"
    assert library_settings["admin_enabled_folders"] == "folder-a,folder-b"
    assert library_settings["hidden_libraries"] == "folder-b"


def test_users_meta_column_helper_rejects_unregistered_columns(monkeypatch, tmp_path):
    from app.domains.users import user_dao

    _use_temp_system_db(monkeypatch, tmp_path)

    try:
        user_dao.ensure_users_meta_column("not_registered")
    except ValueError as exc:
        assert "not_registered" in str(exc)
    else:
        raise AssertionError("expected unregistered users_meta column to be rejected")


def test_users_meta_bootstrap_uses_schema_registry_instead_of_local_ddl():
    source = (_REPO_ROOT / "app/domains/users/user_dao.py").read_text(encoding="utf-8")

    assert "from app.infra.db.schema_bootstrap import (" in source
    assert "ensure_registered_table(cursor, _USERS_META_TABLE)" in source
    assert "registered_alter_columns(_USERS_META_TABLE)" in source
    assert "CREATE TABLE IF NOT EXISTS users_meta" not in source
    assert "ALTER TABLE users_meta ADD COLUMN" not in source


def test_users_meta_consumers_do_not_keep_local_registered_alters():
    sources = {
        "database.py": (_REPO_ROOT / "app/infra/db/database.py").read_text(encoding="utf-8"),
        "media_request_dao.py": (
            _REPO_ROOT / "app/domains/media_requests/media_request_dao.py"
        ).read_text(encoding="utf-8"),
        "point_dao.py": (_REPO_ROOT / "app/domains/points/point_dao.py").read_text(encoding="utf-8"),
    }

    assert 'ensure_registered_table(c, "users_meta")' in sources["database.py"]
    assert 'ensure_registered_table(cursor, "users_meta", {"admin_enabled_folders"})' in sources["media_request_dao.py"]
    assert 'ensure_registered_table(cursor, "users_meta", {"points"})' in sources["point_dao.py"]
    assert "from app.domains.users.user_dao import" not in sources["media_request_dao.py"]
    assert "from app.domains.users.user_dao import" not in sources["point_dao.py"]
    for source in sources.values():
        assert "CREATE TABLE IF NOT EXISTS users_meta" not in source
        assert "ALTER TABLE users_meta ADD COLUMN" not in source
