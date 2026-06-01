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


def test_gap_bootstrap_creates_registry_tables_and_default_config(monkeypatch, tmp_path):
    from app.domains.media_requests import gap_dao
    from app.infra.db.schema_registry import TABLE_SCHEMAS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    gap_dao.ensure_gap_tables()
    gap_dao.ensure_gap_tables()

    with sqlite3.connect(db_path) as conn:
        existing_tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert set(gap_dao.GAP_TABLES).issubset(existing_tables)
        assert _columns(conn, "gap_config") == {"key", "value", "updated_at"}
        assert {"series_id", "series_name", "season_number", "episode_number", "status"}.issubset(
            _columns(conn, "gap_records")
        )
        assert {"series_id", "tmdb_id", "series_name", "marked_at"}.issubset(
            _columns(conn, "gap_perfect_series")
        )
        assert {"id", "result_json", "updated_at"}.issubset(_columns(conn, "gap_scan_cache"))
        row = conn.execute("SELECT value FROM gap_config WHERE key = 'cache_interval_hours'").fetchone()

    assert row == ("6",)
    for table_name in gap_dao.GAP_TABLES:
        assert table_name in TABLE_SCHEMAS


def test_gap_bootstrap_applies_registered_perfect_series_alter(monkeypatch, tmp_path):
    from app.domains.media_requests import gap_dao
    from app.infra.db.schema_registry import TABLE_ALTERS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE gap_perfect_series (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                series_id TEXT,
                series_name TEXT,
                total_seasons INTEGER,
                total_episodes INTEGER,
                marked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(series_id)
            )"""
        )
        conn.commit()

    gap_dao.ensure_gap_tables()
    gap_dao.ensure_gap_tables()

    with sqlite3.connect(db_path) as conn:
        assert "tmdb_id" in _columns(conn, "gap_perfect_series")

    assert TABLE_ALTERS["gap_perfect_series"] == [
        "ALTER TABLE gap_perfect_series ADD COLUMN tmdb_id TEXT"
    ]


def test_gap_bootstrap_migrates_legacy_scan_cache_to_registry_shape(monkeypatch, tmp_path):
    from app.domains.media_requests import gap_dao

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE gap_scan_cache (
                id INTEGER PRIMARY KEY,
                series_id TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        conn.execute("INSERT INTO gap_scan_cache (id, series_id) VALUES (1, 'legacy-series')")
        conn.commit()

    gap_dao.ensure_gap_tables()

    with sqlite3.connect(db_path) as conn:
        columns = _columns(conn, "gap_scan_cache")
        rows = conn.execute("SELECT * FROM gap_scan_cache").fetchall()

    assert columns == {"id", "result_json", "updated_at"}
    assert rows == []


def test_gap_bootstrap_uses_schema_registry_instead_of_local_gap_ddl():
    source = (_REPO_ROOT / "app/domains/media_requests/gap_dao.py").read_text(encoding="utf-8")

    assert "from app.infra.db.schema_registry import TABLE_ALTERS, TABLE_SCHEMAS" in source
    assert "cursor.execute(TABLE_SCHEMAS[table_name])" in source
    for table_name in ("gap_config", "gap_records", "gap_perfect_series", "gap_scan_cache"):
        assert f"\"{table_name}\"" in source

    assert "TABLE_ALTERS.get(\"gap_perfect_series\"" in source
    assert "CREATE TABLE IF NOT EXISTS gap_config" not in source
    assert "CREATE TABLE IF NOT EXISTS gap_records" not in source
    assert "CREATE TABLE IF NOT EXISTS gap_perfect_series" not in source
    assert "CREATE TABLE IF NOT EXISTS gap_scan_cache" not in source
    assert "CREATE TABLE gap_scan_cache" not in source
