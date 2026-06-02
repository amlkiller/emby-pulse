import inspect
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


def _indexes(conn, table_name):
    return {row[1] for row in conn.execute(f"PRAGMA index_list({table_name})").fetchall()}


def test_session_bootstrap_creates_registry_table_and_index(monkeypatch, tmp_path):
    from app.infra.db import session_dao
    from app.infra.db.schema_registry import SYSTEM_TABLES, TABLE_SCHEMAS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    session_dao.ensure_session_table()
    session_dao.ensure_session_table()

    with sqlite3.connect(db_path) as conn:
        columns = _columns(conn, "sessions")
        indexes = _indexes(conn, "sessions")

    assert "sessions" in SYSTEM_TABLES
    assert "sessions" in TABLE_SCHEMAS
    assert {"session_id", "data", "created_at", "expires_at"}.issubset(columns)
    assert "idx_sessions_expires" in indexes


def test_session_dao_paths_work_after_registry_bootstrap(monkeypatch, tmp_path):
    from app.infra.db import session_dao

    _use_temp_system_db(monkeypatch, tmp_path)
    session_dao.ensure_session_table()

    session_dao.create_session("s1", {"user": "u1"}, created_at=100.0, expires_at=200.0)
    row = session_dao.get_session("s1", now=150.0, absolute_cutoff=50.0)
    assert row["data"] == '{"user": "u1"}'
    assert row["created_at"] == 100.0

    session_dao.update_session("s1", {"user": "u2"})
    row = session_dao.get_session("s1", now=150.0, absolute_cutoff=50.0)
    assert row["data"] == '{"user": "u2"}'

    assert session_dao.cleanup_expired_sessions(now=250.0) == 1
    assert session_dao.get_session("s1", now=150.0, absolute_cutoff=50.0) is None

    session_dao.create_session("s2", {"user": "u3"}, created_at=100.0, expires_at=300.0)
    session_dao.delete_session("s2")
    assert session_dao.get_session("s2", now=150.0, absolute_cutoff=50.0) is None


def test_session_clear_if_table_exists_preserves_missing_table_behavior(monkeypatch, tmp_path):
    from app.infra.db import session_dao

    _use_temp_system_db(monkeypatch, tmp_path)

    assert session_dao.clear_sessions_if_table_exists() is None

    session_dao.ensure_session_table()
    session_dao.create_session("s1", {}, created_at=100.0, expires_at=200.0)
    session_dao.create_session("s2", {}, created_at=100.0, expires_at=200.0)

    assert session_dao.clear_sessions_if_table_exists() == 2
    assert session_dao.clear_sessions_if_table_exists() == 0


def test_session_bootstrap_uses_schema_registry_instead_of_local_table_ddl():
    from app.infra.db import session_dao

    source = inspect.getsource(session_dao)

    assert "ensure_registered_table(cursor, SESSION_TABLE)" in source
    assert "CREATE TABLE IF NOT EXISTS sessions" not in source
    assert "CREATE INDEX IF NOT EXISTS idx_sessions_expires" in source
