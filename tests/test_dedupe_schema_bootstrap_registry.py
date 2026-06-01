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


def test_dedupe_bootstrap_creates_registry_tables(monkeypatch, tmp_path):
    from app.domains.playback import dedupe_dao
    from app.infra.db.schema_registry import TABLE_SCHEMAS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    dedupe_dao.init_dedupe_tables()
    dedupe_dao.init_dedupe_tables()

    with sqlite3.connect(db_path) as conn:
        existing_tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert set(dedupe_dao.DEDUPE_TABLES).issubset(existing_tables)
        assert {"group_key", "title", "created_at"}.issubset(_columns(conn, "dedupe_whitelist"))
        assert {"key", "value", "updated_at"}.issubset(_columns(conn, "dedupe_config"))
        assert {
            "group_key",
            "tmdb_id",
            "media_type",
            "title",
            "season_num",
            "episode_num",
            "item_id",
            "is_recommended_del",
            "is_exempt",
        }.issubset(_columns(conn, "dedupe_results"))

    for table_name in dedupe_dao.DEDUPE_TABLES:
        assert table_name in TABLE_SCHEMAS


def test_dedupe_bootstrap_applies_registered_result_alters(monkeypatch, tmp_path):
    from app.domains.playback import dedupe_dao
    from app.infra.db.schema_registry import TABLE_ALTERS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE dedupe_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                media_type TEXT,
                title TEXT,
                item_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        conn.commit()

    dedupe_dao.init_dedupe_tables()
    dedupe_dao.init_dedupe_tables()

    with sqlite3.connect(db_path) as conn:
        columns = _columns(conn, "dedupe_results")

    for alter_sql in TABLE_ALTERS["dedupe_results"]:
        column_name = alter_sql.split("ADD COLUMN ", 1)[1].split(" ", 1)[0]
        assert column_name in columns


def test_dedupe_bootstrap_applies_registered_whitelist_alter(monkeypatch, tmp_path):
    from app.domains.playback import dedupe_dao

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE dedupe_whitelist (
                group_key TEXT PRIMARY KEY,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        conn.commit()

    dedupe_dao.init_dedupe_tables()
    dedupe_dao.init_dedupe_tables()

    with sqlite3.connect(db_path) as conn:
        assert "title" in _columns(conn, "dedupe_whitelist")


def test_dedupe_bootstrap_migrates_legacy_whitelist_to_registry_shape(monkeypatch, tmp_path):
    from app.domains.playback import dedupe_dao

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE dedupe_whitelist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id TEXT,
                item_name TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        conn.execute(
            "INSERT INTO dedupe_whitelist (item_id, item_name, created_at) VALUES (?, ?, ?)",
            ("group-a", "Title A", "2026-06-02 10:00:00"),
        )
        conn.execute(
            "INSERT INTO dedupe_whitelist (item_id, item_name, created_at) VALUES (?, ?, ?)",
            ("", "Missing ID", "2026-06-02 11:00:00"),
        )
        conn.commit()

    dedupe_dao.init_dedupe_tables()

    with sqlite3.connect(db_path) as conn:
        columns = _columns(conn, "dedupe_whitelist")
        rows = conn.execute("SELECT group_key, title, created_at FROM dedupe_whitelist").fetchall()

    assert columns == {"group_key", "title", "created_at"}
    assert rows == [("group-a", "Title A", "2026-06-02 10:00:00")]


def test_dedupe_bootstrap_uses_schema_registry_instead_of_local_dedupe_ddl():
    source = (_REPO_ROOT / "app/domains/playback/dedupe_dao.py").read_text(encoding="utf-8")

    assert "from app.infra.db.schema_registry import TABLE_ALTERS, TABLE_SCHEMAS" in source
    assert "TABLE_SCHEMAS[\"dedupe_whitelist\"]" in source
    assert "cursor.execute(TABLE_SCHEMAS[table_name])" in source
    assert "TABLE_ALTERS.get(table_name, [])" in source

    assert "CREATE TABLE IF NOT EXISTS dedupe_whitelist" not in source
    assert "CREATE TABLE IF NOT EXISTS dedupe_results" not in source
    assert "CREATE TABLE IF NOT EXISTS dedupe_config" not in source
    assert "ALTER TABLE dedupe_results ADD COLUMN" not in source
    assert "ALTER TABLE dedupe_whitelist ADD COLUMN title" not in source
