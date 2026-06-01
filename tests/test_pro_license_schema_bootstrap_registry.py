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


def test_pro_license_bootstrap_creates_registry_table(monkeypatch, tmp_path):
    from app.domains.system import pro_license_dao
    from app.infra.db.schema_registry import TABLE_SCHEMAS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    pro_license_dao.ensure_pro_schema()
    pro_license_dao.ensure_pro_schema()

    with sqlite3.connect(db_path) as conn:
        columns = _columns(conn, "sys_license")

    assert "sys_license" in TABLE_SCHEMAS
    assert {
        "license_key",
        "machine_id",
        "pro_token",
        "status",
        "expire_date",
        "last_checked",
        "max_devices",
        "current_devices",
    }.issubset(columns)


def test_pro_license_bootstrap_applies_registered_alters(monkeypatch, tmp_path):
    from app.domains.system import pro_license_dao
    from app.infra.db.schema_registry import TABLE_ALTERS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE sys_license (
                license_key TEXT,
                machine_id TEXT,
                status TEXT DEFAULT 'pro'
            )"""
        )
        conn.execute(
            "INSERT INTO sys_license (license_key, machine_id, status) VALUES (?, ?, ?)",
            ("legacy-key", "machine-a", "pro"),
        )
        conn.commit()

    pro_license_dao.ensure_pro_schema()
    pro_license_dao.ensure_pro_schema()

    with sqlite3.connect(db_path) as conn:
        columns = _columns(conn, "sys_license")
        row = conn.execute(
            """
            SELECT license_key, machine_id, status, pro_token, expire_date,
                   max_devices, current_devices
            FROM sys_license
            """
        ).fetchone()

    assert TABLE_ALTERS["sys_license"] == [
        "ALTER TABLE sys_license ADD COLUMN pro_token TEXT",
        "ALTER TABLE sys_license ADD COLUMN expire_date DATETIME",
        "ALTER TABLE sys_license ADD COLUMN last_checked DATETIME",
        "ALTER TABLE sys_license ADD COLUMN max_devices INTEGER",
        "ALTER TABLE sys_license ADD COLUMN current_devices INTEGER",
    ]
    registered_alters = "\n".join(TABLE_ALTERS["sys_license"])
    assert "DEFAULT CURRENT_TIMESTAMP" not in registered_alters
    for alter_sql in TABLE_ALTERS["sys_license"]:
        column_name = alter_sql.split("ADD COLUMN ", 1)[1].split(" ", 1)[0]
        assert column_name in columns
    assert row == ("legacy-key", "machine-a", "pro", None, None, None, None)


def test_pro_license_replace_and_status_shape_after_registry_bootstrap(monkeypatch, tmp_path):
    from app.domains.system import pro_license_dao

    _use_temp_system_db(monkeypatch, tmp_path)
    pro_license_dao.ensure_pro_schema()

    pro_license_dao.replace_license("first-key", "machine-a")
    pro_license_dao.replace_license("second-key", "machine-b", status="trial")

    row = pro_license_dao.get_license_status()

    assert row["license_key"] == "second-key"
    assert row["machine_id"] == "machine-b"
    assert row["status"] == "trial"
    assert row["max_devices"] is None
    assert row["current_devices"] is None


def test_pro_status_route_keeps_existing_device_payload(monkeypatch, tmp_path):
    from app.domains.system import pro
    from app.domains.system import pro_license_dao

    _use_temp_system_db(monkeypatch, tmp_path)
    pro_license_dao.ensure_pro_schema()
    pro_license_dao.replace_license("abcdef123456", "machine-a")
    monkeypatch.setattr(pro, "is_admin_user", lambda request: True)

    import asyncio

    response = asyncio.run(pro.get_pro_status(request=object()))

    assert response == {
        "status": "success",
        "data": {
            "license": {
                "license_key": "abcdef12****",
                "machine_id": "machine-a",
                "status": "pro",
            },
            "device": {"max_devices": 10, "current_devices": 0},
        },
    }


def test_pro_license_bootstrap_uses_schema_registry_instead_of_local_ddl():
    source = (_REPO_ROOT / "app/domains/system/pro_license_dao.py").read_text(encoding="utf-8")

    assert "from app.infra.db.schema_registry import TABLE_ALTERS, TABLE_SCHEMAS" in source
    assert "TABLE_SCHEMAS[\"sys_license\"]" in source
    assert "TABLE_ALTERS.get(table_name, [])" in source
    assert "CREATE TABLE IF NOT EXISTS sys_license" not in source
    assert "ALTER TABLE sys_license ADD COLUMN" not in source
