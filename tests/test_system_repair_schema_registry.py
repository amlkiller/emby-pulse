import sqlite3
import sys
from pathlib import Path


_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from app.domains.system import system_tool_dao  # noqa: E402
from app.infra.db.schema_registry import PLAYBACK_SCHEMA, TABLE_ALTERS, TABLE_INDEXES, TABLE_SCHEMAS  # noqa: E402
from app.infra.db.system_store import system_store  # noqa: E402


REPAIRED_TABLES = [
    "PlaybackActivity",
    "users_meta",
    "invitations",
    "tv_calendar_cache",
    "media_requests",
    "request_users",
    "insight_ignores",
    "gap_records",
]


def _columns(conn, table_name):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _use_temp_system_db(monkeypatch, tmp_path):
    db_path = tmp_path / "system_store.db"
    monkeypatch.setattr(system_store, "db_path", str(db_path))
    return db_path


def test_repair_creates_missing_tables_from_schema_registry(monkeypatch, tmp_path):
    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    results = system_tool_dao.repair_core_system_tables()

    assert "已修复: 播放活动主表" in results
    assert "已修复: 用户元数据表" in results
    assert "已修复: 求片主表" in results

    with sqlite3.connect(db_path) as conn:
        existing_tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert set(REPAIRED_TABLES).issubset(existing_tables)

        playback_columns = _columns(conn, "PlaybackActivity")
        for column_name in ("RemoteEndPoint", "Location", "ISP", "ClientName", "ItemType"):
            assert column_name in playback_columns
            assert column_name in PLAYBACK_SCHEMA

        users_meta_columns = _columns(conn, "users_meta")
        assert "req_free" in users_meta_columns
        assert any("req_free" in alter_sql for alter_sql in TABLE_ALTERS["users_meta"])

        media_request_columns = _columns(conn, "media_requests")
        for column_name in ("episodes", "request_type", "series_id"):
            assert column_name in media_request_columns
            assert column_name in TABLE_SCHEMAS["media_requests"]
        indexes = {
            row[1]
            for row in conn.execute(
                "SELECT type, name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }

    assert "idx_users_meta_expire" in indexes
    assert "idx_media_requests_status" in indexes
    assert "idx_playback_date" in indexes
    assert any("idx_users_meta_expire" in sql for sql in TABLE_INDEXES["users_meta"])


def test_repair_applies_registered_alters_to_existing_tables(monkeypatch, tmp_path):
    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE PlaybackActivity (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                UserId TEXT,
                UserName TEXT
            )"""
        )
        conn.execute(
            """CREATE TABLE media_requests (
                tmdb_id INTEGER,
                season INTEGER DEFAULT 0,
                PRIMARY KEY (tmdb_id, season)
            )"""
        )
        conn.execute(
            """CREATE TABLE invitations (
                code TEXT PRIMARY KEY,
                days INTEGER
            )"""
        )
        conn.commit()

    results = system_tool_dao.repair_core_system_tables()

    assert "已升级: 邀请码模板字段" in results
    assert "已升级: 播放活动主表字段 RemoteEndPoint" in results
    assert "已升级: 求片主表字段 episodes" in results

    with sqlite3.connect(db_path) as conn:
        assert {"RemoteEndPoint", "Location", "ISP", "ClientName", "ItemType"}.issubset(
            _columns(conn, "PlaybackActivity")
        )
        assert {"episodes", "request_type", "series_id"}.issubset(
            _columns(conn, "media_requests")
        )
        assert {"template_user_id", "type", "routes", "route_mode"}.issubset(
            _columns(conn, "invitations")
        )

    assert system_tool_dao.repair_core_system_tables() == []


def test_repair_helper_uses_schema_registry_imports_instead_of_local_repair_ddl():
    source = (_repo_root / "app/domains/system/system_tool_dao.py").read_text(encoding="utf-8")

    assert "from app.infra.db.schema_bootstrap import apply_registered_indexes, ensure_registered_table" in source
    assert "from app.infra.db.schema_registry import PLAYBACK_SCHEMA, SYSTEM_TABLES, TABLE_ALTERS, TABLE_SCHEMAS" in source
    assert "apply_registered_indexes(cursor, table_name)" in source
    for table_name in REPAIRED_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" not in source
