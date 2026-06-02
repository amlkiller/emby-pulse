import inspect
import sqlite3
import sys
import time
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


def test_audit_logger_bootstrap_creates_registry_table_and_indexes(monkeypatch, tmp_path):
    from app.infra.db import audit_logger_dao
    from app.infra.db.schema_registry import SYSTEM_TABLES, TABLE_SCHEMAS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    audit_logger_dao.ensure_audit_table()
    audit_logger_dao.ensure_audit_table()

    with sqlite3.connect(db_path) as conn:
        columns = _columns(conn, "audit_logs")
        indexes = _indexes(conn, "audit_logs")

    assert "audit_logs" in SYSTEM_TABLES
    assert "audit_logs" in TABLE_SCHEMAS
    assert {
        "id",
        "timestamp",
        "datetime",
        "user_id",
        "user_name",
        "action",
        "resource_type",
        "resource_id",
        "ip_address",
        "user_agent",
        "details",
        "status",
        "created_at",
    }.issubset(columns)
    assert {"idx_audit_timestamp", "idx_audit_user_id", "idx_audit_action"}.issubset(indexes)


def test_audit_logger_dao_paths_work_after_registry_bootstrap(monkeypatch, tmp_path):
    from app.infra.db import audit_logger_dao

    _use_temp_system_db(monkeypatch, tmp_path)
    audit_logger_dao.ensure_audit_table()

    audit_logger_dao.insert_audit_log(
        "login",
        user_id="u1",
        user_name="User One",
        resource_type="session",
        resource_id="s1",
        ip_address="203.0.113.10",
        details={"method": "password"},
    )
    audit_logger_dao.insert_audit_log("login_failed", user_id="u2", user_name="User Two", status="failed")

    login_rows = audit_logger_dao.list_audit_logs(action="login", limit=10)
    stats = audit_logger_dao.get_audit_stats_since(0)
    deleted = audit_logger_dao.cleanup_audit_logs_before(time.time() + 1)

    assert len(login_rows) == 1
    assert login_rows[0]["user_id"] == "u1"
    assert login_rows[0]["details"] == '{"method": "password"}'
    assert stats["total"] == 2
    assert {"action": "login", "count": 1} in stats["by_action"]
    assert {"action": "login_failed", "count": 1} in stats["failed"]
    assert deleted == 2


def test_audit_logger_bootstrap_uses_schema_registry_instead_of_local_table_ddl():
    from app.infra.db import audit_logger_dao

    source = inspect.getsource(audit_logger_dao)

    assert 'ensure_registered_table(cursor, "audit_logs")' in source
    assert "CREATE TABLE IF NOT EXISTS audit_logs" not in source
    assert "CREATE INDEX IF NOT EXISTS idx_audit_timestamp" in source
