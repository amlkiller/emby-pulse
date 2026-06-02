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


def test_point_core_bootstrap_creates_registry_tables_and_defaults(monkeypatch, tmp_path):
    from app.domains.points import point_dao
    from app.infra.db.schema_registry import SYSTEM_TABLES, TABLE_SCHEMAS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    point_dao.ensure_points_schema()
    point_dao.ensure_points_schema()

    with sqlite3.connect(db_path) as conn:
        point_log_columns = _columns(conn, "point_logs")
        point_config_columns = _columns(conn, "point_config")
        users_meta_columns = _columns(conn, "users_meta")
        point_game_tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if row[0].startswith("point_") or row[0].startswith("pk_")
        }

    assert "point_logs" in SYSTEM_TABLES
    assert "point_config" in SYSTEM_TABLES
    assert "point_logs" in TABLE_SCHEMAS
    assert "point_config" in TABLE_SCHEMAS
    assert {"id", "user_id", "username", "action", "amount", "balance", "created_at"}.issubset(
        point_log_columns
    )
    assert {"key", "value"}.issubset(point_config_columns)
    assert "points" in users_meta_columns
    assert {
        "point_checkin_streak",
        "point_red_packets",
        "point_red_packet_logs",
        "point_transfer_logs",
        "point_rob_logs",
        "pk_invitations",
        "pk_logs",
    }.issubset(point_game_tables)

    config = point_dao.get_point_config()
    assert config["enable_points"] == "1"
    assert config["checkin_min"] == "10"
    assert "store_items" in config


def test_point_core_dao_paths_work_after_registry_bootstrap(monkeypatch, tmp_path):
    from app.domains.points import point_dao

    _use_temp_system_db(monkeypatch, tmp_path)

    point_dao.ensure_points_schema()
    point_dao.save_point_config_values({"checkin_min": 20, "nested": {"enabled": True}})
    updated = point_dao.get_point_config()
    updated_count = point_dao.batch_update_user_points(
        ["user-1"],
        15,
        "测试",
        {"user-1": "测试用户"},
    )
    balance = point_dao.get_user_points_balance("user-1")
    logs = point_dao.list_point_logs(user_id="user-1")

    assert updated["checkin_min"] == "20"
    assert updated["nested"] == '{"enabled": true}'
    assert updated_count == 1
    assert balance == 15
    assert logs["total"] == 1
    assert logs["logs"][0]["username"] == "测试用户"
    assert logs["logs"][0]["amount"] == 15


def test_point_core_bootstrap_uses_schema_registry_for_owned_tables_only():
    source = (_REPO_ROOT / "app/domains/points/point_dao.py").read_text(encoding="utf-8")

    assert "from app.infra.db.schema_bootstrap import ensure_registered_table" in source
    assert 'ensure_registered_table(cursor, "users_meta", {"points"})' in source
    assert 'ensure_registered_table(cursor, "point_logs")' in source
    assert 'ensure_registered_table(cursor, "point_config")' in source
    assert "CREATE TABLE IF NOT EXISTS point_logs" not in source
    assert "CREATE TABLE IF NOT EXISTS point_config" not in source
    assert "CREATE TABLE IF NOT EXISTS point_checkin_streak" in source
    assert "CREATE TABLE IF NOT EXISTS pk_invitations" in source
