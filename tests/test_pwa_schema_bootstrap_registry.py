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


def test_pwa_bootstrap_creates_registry_tables(monkeypatch, tmp_path):
    from app.domains.pwa import pwa_dao
    from app.infra.db.schema_registry import SYSTEM_TABLES, TABLE_SCHEMAS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    pwa_dao.ensure_pwa_config_table()
    pwa_dao.ensure_user_pwa_icons_table()
    pwa_dao.ensure_pwa_config_table()
    pwa_dao.ensure_user_pwa_icons_table()

    with sqlite3.connect(db_path) as conn:
        pwa_config_columns = _columns(conn, "pwa_config")
        user_icon_columns = _columns(conn, "user_pwa_icons")

    assert "pwa_config" in SYSTEM_TABLES
    assert "user_pwa_icons" in SYSTEM_TABLES
    assert "pwa_config" in TABLE_SCHEMAS
    assert "user_pwa_icons" in TABLE_SCHEMAS
    assert {"key", "value"}.issubset(pwa_config_columns)
    assert {"user_id", "icon_id"}.issubset(user_icon_columns)


def test_pwa_dao_paths_work_after_registry_bootstrap(monkeypatch, tmp_path):
    from app.domains.pwa import pwa_dao

    _use_temp_system_db(monkeypatch, tmp_path)

    pwa_dao.save_pwa_config_value("app_name", "EmbyPulse")
    pwa_dao.save_pwa_config_value("default_icon", "icon-main")
    pwa_dao.set_user_pwa_icon("user-1", "icon-alt")

    assert pwa_dao.get_pwa_config_values() == {
        "app_name": "EmbyPulse",
        "default_icon": "icon-main",
    }
    assert pwa_dao.get_user_pwa_icon("user-1") == "icon-alt"
    assert pwa_dao.get_user_pwa_icon("missing") is None


def test_pwa_bootstrap_uses_schema_registry_instead_of_local_ddl():
    source = (_REPO_ROOT / "app/domains/pwa/pwa_dao.py").read_text(encoding="utf-8")

    assert "from app.infra.db.schema_bootstrap import ensure_registered_table" in source
    assert 'ensure_registered_table(cursor, "pwa_config")' in source
    assert 'ensure_registered_table(cursor, "user_pwa_icons")' in source
    assert "CREATE TABLE IF NOT EXISTS pwa_config" not in source
    assert "CREATE TABLE IF NOT EXISTS user_pwa_icons" not in source
