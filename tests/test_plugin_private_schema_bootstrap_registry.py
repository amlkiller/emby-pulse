import sqlite3
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


PLUGIN_PRIVATE_TABLES = (
    "temp_accounts",
    "temp_account_password_history",
    "season_poster_logs",
    "season_poster_cache",
    "emby_restart_history",
    "smart_collections",
    "smart_collection_items",
    "smart_collection_sync_logs",
)


def _use_temp_system_db(monkeypatch, tmp_path):
    from app.infra.db.system_store import system_store

    db_path = tmp_path / "system_store.db"
    monkeypatch.setattr(system_store, "db_path", str(db_path))
    return db_path


def _columns(conn, table_name):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def test_plugin_private_tables_are_registered():
    from app.infra.db.schema_registry import SYSTEM_TABLES, TABLE_ALTERS, TABLE_SCHEMAS

    for table_name in PLUGIN_PRIVATE_TABLES:
        assert table_name in SYSTEM_TABLES
        assert table_name in TABLE_SCHEMAS

    assert TABLE_ALTERS["temp_accounts"] == [
        "ALTER TABLE temp_accounts ADD COLUMN allow_routes TEXT DEFAULT ''",
        "ALTER TABLE temp_accounts ADD COLUMN block_routes TEXT DEFAULT ''",
        "ALTER TABLE temp_accounts ADD COLUMN tags TEXT DEFAULT ''",
        "ALTER TABLE temp_accounts ADD COLUMN req_free INTEGER DEFAULT 0",
        "ALTER TABLE temp_accounts ADD COLUMN req_free_count INTEGER DEFAULT -1",
    ]


def test_plugin_private_bootstraps_create_registry_tables(monkeypatch, tmp_path):
    from app.plugins.emby_restart import emby_restart_dao
    from app.plugins.season_poster_updater import season_poster_dao
    from app.plugins.smart_collections import smart_collection_dao
    from app.plugins.temp_account import temp_account_dao

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    temp_account_dao.ensure_temp_account_tables()
    season_poster_dao.ensure_season_poster_tables()
    emby_restart_dao.ensure_emby_restart_history_table()
    smart_collection_dao.ensure_smart_collection_tables()

    temp_account_dao.ensure_temp_account_tables()
    season_poster_dao.ensure_season_poster_tables()
    emby_restart_dao.ensure_emby_restart_history_table()
    smart_collection_dao.ensure_smart_collection_tables()

    with sqlite3.connect(db_path) as conn:
        table_columns = {table_name: _columns(conn, table_name) for table_name in PLUGIN_PRIVATE_TABLES}

    assert {
        "username",
        "emby_user_id",
        "current_password",
        "allow_routes",
        "block_routes",
        "req_free",
        "req_free_count",
        "tags",
    }.issubset(table_columns["temp_accounts"])
    assert {"account_id", "old_password", "new_password", "notify_sent"}.issubset(
        table_columns["temp_account_password_history"]
    )
    assert {"series_id", "series_name", "season_number", "success", "message"}.issubset(
        table_columns["season_poster_logs"]
    )
    assert {"series_id", "season_count", "last_season_number", "last_updated"}.issubset(
        table_columns["season_poster_cache"]
    )
    assert {"time", "mode", "success", "detail"}.issubset(table_columns["emby_restart_history"])
    assert {"name", "source_config", "min_rating", "last_sync", "last_count"}.issubset(
        table_columns["smart_collections"]
    )
    assert {"collection_id", "item_id", "sort_order", "added_at"}.issubset(
        table_columns["smart_collection_items"]
    )
    assert {"collection_id", "action", "status", "message", "count"}.issubset(
        table_columns["smart_collection_sync_logs"]
    )


def test_temp_account_legacy_table_gets_registered_alters(monkeypatch, tmp_path):
    from app.plugins.temp_account import temp_account_dao

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE temp_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                emby_user_id TEXT,
                current_password TEXT NOT NULL,
                template_user_id TEXT,
                auto_update_enabled INTEGER DEFAULT 1,
                update_interval_hours INTEGER DEFAULT 24,
                update_interval_minutes INTEGER DEFAULT 0,
                last_password_update TEXT,
                next_password_update TEXT,
                notify_tg INTEGER DEFAULT 1,
                notify_wecom INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                remark TEXT DEFAULT 'temp account'
            )
            """
        )
        conn.commit()

    temp_account_dao.ensure_temp_account_tables()
    temp_account_dao.ensure_temp_account_tables()

    with sqlite3.connect(db_path) as conn:
        columns = _columns(conn, "temp_accounts")

    assert {"allow_routes", "block_routes", "tags", "req_free", "req_free_count"}.issubset(columns)


def test_plugin_private_dao_smoke_paths_work_after_registry_bootstrap(monkeypatch, tmp_path):
    from app.infra.db.schema_bootstrap import ensure_registered_table
    from app.plugins.emby_restart import emby_restart_dao
    from app.plugins.season_poster_updater import season_poster_dao
    from app.plugins.smart_collections import smart_collection_dao
    from app.plugins.temp_account import temp_account_dao
    from app.infra.db.system_store import system_store

    _use_temp_system_db(monkeypatch, tmp_path)
    with system_store.connect() as conn:
        ensure_registered_table(conn.cursor(), "users_meta")
        conn.commit()

    temp_account_dao.create_temp_account_with_meta(
        username="temp-user",
        emby_user_id="emby-1",
        password="old-pass",
        template_user_id="tpl-1",
        allow_routes="route-a",
        block_routes="",
        req_free=1,
        req_free_count=2,
        update_interval_hours=12,
        update_interval_minutes=30,
        notify_tg=1,
        notify_wecom=0,
        now_iso="2026-06-02T10:00:00",
        next_update_iso="2026-06-03T10:00:00",
        remark="temp",
        tags="",
    )
    account = temp_account_dao.list_temp_accounts()[0]
    temp_account_dao.update_temp_account_password(
        account_id=account["id"],
        new_password="new-pass",
        last_update="2026-06-02T11:00:00",
        next_update="2026-06-03T11:00:00",
        old_password="old-pass",
    )

    season_poster_dao.save_season_poster_log(
        "2026-06-02T12:00:00", "series-1", "Series One", 1, "old.jpg", "new.jpg", True, "ok"
    )
    season_poster_dao.save_cached_season_poster("series-1", "Series One", 2, 1, "2026-06-02T12:01:00")

    emby_restart_dao.create_emby_restart_history(
        {"time": "2026-06-02T12:02:00", "mode": "soft", "success": True, "detail": "done"}
    )

    collection_id = smart_collection_dao.create_smart_collection(
        {"name": "Trending", "source_config": {"window": "day"}, "min_rating": 8}, "2026-06-02T12:03:00"
    )
    smart_collection_dao.replace_smart_collection_items(collection_id, ["item-1", "item-2"], "2026-06-02T12:04:00")
    smart_collection_dao.add_smart_collection_log(collection_id, "sync", "success", "added", 2, "2026-06-02T12:05:00")
    smart_collection_dao.set_smart_collection_sync_state(collection_id, "2026-06-02T12:06:00", 2)

    assert temp_account_dao.get_temp_account(account["id"])["current_password"] == "new-pass"
    assert temp_account_dao.list_temp_account_password_history(account["id"])[0]["old_password"] == "old-pass"
    assert season_poster_dao.count_updated_series() == 1
    assert season_poster_dao.get_cached_season_poster("series-1")["season_count"] == 2
    assert emby_restart_dao.list_emby_restart_history()[0]["detail"] == "done"
    assert smart_collection_dao.get_smart_collection(collection_id)["last_count"] == 2
    assert len(smart_collection_dao.list_smart_collection_items(collection_id)) == 2
    assert smart_collection_dao.list_smart_collection_logs()[0]["collection_name"] == "Trending"


def test_plugin_private_bootstraps_do_not_keep_local_registry_owned_ddl():
    sources = {
        "temp_account_dao.py": (_REPO_ROOT / "app/plugins/temp_account/temp_account_dao.py").read_text(encoding="utf-8"),
        "season_poster_dao.py": (
            _REPO_ROOT / "app/plugins/season_poster_updater/season_poster_dao.py"
        ).read_text(encoding="utf-8"),
        "emby_restart_dao.py": (_REPO_ROOT / "app/plugins/emby_restart/emby_restart_dao.py").read_text(
            encoding="utf-8"
        ),
        "smart_collection_dao.py": (
            _REPO_ROOT / "app/plugins/smart_collections/smart_collection_dao.py"
        ).read_text(encoding="utf-8"),
    }

    assert "from app.infra.db.schema_bootstrap import ensure_registered_table" in sources["temp_account_dao.py"]
    assert "ensure_registered_table(cursor, table_name)" in sources["temp_account_dao.py"]
    assert "ensure_registered_table(cursor, table_name)" in sources["season_poster_dao.py"]
    assert 'ensure_registered_table(cursor, "emby_restart_history")' in sources["emby_restart_dao.py"]
    assert "ensure_registered_table(cursor, table_name)" in sources["smart_collection_dao.py"]

    for source in sources.values():
        for table_name in PLUGIN_PRIVATE_TABLES:
            assert f"CREATE TABLE IF NOT EXISTS {table_name}" not in source

    assert "ALTER TABLE temp_accounts ADD COLUMN" not in sources["temp_account_dao.py"]
