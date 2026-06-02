import sqlite3
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


POINT_GAME_TABLES = (
    "lottery_tickets",
    "lottery_results",
    "lottery_winners",
    "scratch_cards",
    "scratch_card_slots",
    "point_checkin_streak",
    "point_red_packets",
    "point_red_packet_logs",
    "point_transfer_logs",
    "point_rob_logs",
    "pk_invitations",
    "pk_logs",
)


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
        lottery_columns = _columns(conn, "lottery_tickets")
        scratch_columns = _columns(conn, "scratch_cards")
        red_packet_columns = _columns(conn, "point_red_packets")
        pk_invitation_columns = _columns(conn, "pk_invitations")

    assert "point_logs" in SYSTEM_TABLES
    assert "point_config" in SYSTEM_TABLES
    assert "point_logs" in TABLE_SCHEMAS
    assert "point_config" in TABLE_SCHEMAS
    for table_name in POINT_GAME_TABLES:
        assert table_name in SYSTEM_TABLES
        assert table_name in TABLE_SCHEMAS
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
    assert {"user_id", "numbers", "cost", "draw_date", "created_at"}.issubset(lottery_columns)
    assert {"chat_id", "message_id"}.issubset(scratch_columns)
    assert "message_id" in red_packet_columns
    assert {"challenger_tg_name", "target_tg_name", "command_message_id"}.issubset(
        pk_invitation_columns
    )

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


def test_point_game_dao_paths_work_after_registry_bootstrap(monkeypatch, tmp_path):
    from app.domains.points import point_dao
    from app.infra.db.system_store import system_store

    _use_temp_system_db(monkeypatch, tmp_path)

    point_dao.ensure_points_schema()
    system_store.execute(
        "INSERT INTO users_meta (user_id, points, created_at) VALUES (?, ?, ?)",
        ("user-1", 1000, "2026-06-02 00:00:00"),
    )
    system_store.execute(
        "INSERT INTO users_meta (user_id, points, created_at) VALUES (?, ?, ?)",
        ("user-2", 0, "2026-06-02 00:00:00"),
    )

    lottery_result = point_dao.buy_lottery_tickets(
        "user-1",
        "Alice",
        2,
        10,
        5,
        "2099-01-01",
        ["01,02,03", "04,05,06"],
    )
    assert lottery_result["status"] == "success"
    assert lottery_result["new_points"] == 980
    assert point_dao.list_lottery_ticket_numbers("user-1", "2099-01-01") == [
        "01,02,03",
        "04,05,06",
    ]

    red_packet = point_dao.create_red_packet(100, 1, "chat-1", "user-1", "Alice")
    assert red_packet["status"] == "success"
    grabbed = point_dao.grab_red_packet(red_packet["packet_id"], "user-2", "Bob")
    assert grabbed["status"] == "success"
    assert grabbed["amount"] == 100
    assert grabbed["is_last_one"] is True
    assert grabbed["chat_id"] == "chat-1"

    scratch_card = point_dao.create_scratch_card(
        total_slots=1,
        price=10,
        created_by="admin",
        chat_id="chat-2",
        prizes=[50],
    )
    assert scratch_card["status"] == "success"
    scratched = point_dao.update_scratch_card_slot(
        scratch_card["card_id"],
        1,
        "user-2",
        "bob",
        10,
        "Bob",
    )
    assert scratched["status"] == "success"
    assert scratched["new_filled"] == 1
    assert scratched["chat_id"] == "chat-2"


def test_point_game_registered_alters_upgrade_legacy_table_shapes(monkeypatch, tmp_path):
    from app.domains.points import point_dao
    from app.infra.db.schema_registry import TABLE_ALTERS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE scratch_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                total_slots INTEGER DEFAULT 9
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE point_red_packets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                total_amount INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE pk_invitations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                challenger_id TEXT,
                target_id TEXT
            )
            """
        )

    point_dao.ensure_points_schema()

    with sqlite3.connect(db_path) as conn:
        assert {"chat_id", "message_id"}.issubset(_columns(conn, "scratch_cards"))
        assert "message_id" in _columns(conn, "point_red_packets")
        assert {"challenger_tg_name", "target_tg_name", "command_message_id"}.issubset(
            _columns(conn, "pk_invitations")
        )

    assert TABLE_ALTERS["scratch_cards"] == [
        "ALTER TABLE scratch_cards ADD COLUMN chat_id TEXT DEFAULT ''",
        "ALTER TABLE scratch_cards ADD COLUMN message_id INTEGER DEFAULT 0",
    ]
    assert TABLE_ALTERS["point_red_packets"] == [
        "ALTER TABLE point_red_packets ADD COLUMN message_id TEXT"
    ]
    assert TABLE_ALTERS["pk_invitations"] == [
        "ALTER TABLE pk_invitations ADD COLUMN challenger_tg_name TEXT",
        "ALTER TABLE pk_invitations ADD COLUMN target_tg_name TEXT",
        "ALTER TABLE pk_invitations ADD COLUMN command_message_id TEXT",
    ]


def test_point_lottery_helper_uses_registry_owned_tables(monkeypatch, tmp_path):
    from app.domains.points import point_dao

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    point_dao.ensure_lottery_table()
    point_dao.ensure_lottery_table()

    with sqlite3.connect(db_path) as conn:
        assert {"user_id", "numbers", "draw_date"}.issubset(_columns(conn, "lottery_tickets"))
        assert {"draw_date", "winning_numbers", "total_pool"}.issubset(
            _columns(conn, "lottery_results")
        )
        assert {"user_id", "ticket_id", "prize_amount", "draw_date"}.issubset(
            _columns(conn, "lottery_winners")
        )


def test_point_core_bootstrap_uses_schema_registry_for_owned_tables_only():
    sources = {
        "point_dao.py": (_REPO_ROOT / "app/domains/points/point_dao.py").read_text(encoding="utf-8"),
        "lottery_dao.py": (_REPO_ROOT / "app/domains/points/lottery_dao.py").read_text(encoding="utf-8"),
        "red_packet_dao.py": (_REPO_ROOT / "app/domains/points/red_packet_dao.py").read_text(encoding="utf-8"),
    }
    combined_source = "\n".join(sources.values())

    assert "from app.infra.db.schema_bootstrap import ensure_registered_table" in sources["point_dao.py"]
    assert "from app.infra.db.schema_bootstrap import ensure_registered_table" in sources["lottery_dao.py"]
    assert 'ensure_registered_table(cursor, "users_meta", {"points"})' in sources["point_dao.py"]
    assert 'ensure_registered_table(cursor, "point_logs")' in sources["point_dao.py"]
    assert 'ensure_registered_table(cursor, "point_config")' in sources["point_dao.py"]
    assert "for table_name in _POINT_GAME_TABLES:" in sources["point_dao.py"]
    assert "ensure_registered_table(cursor, table_name)" in sources["point_dao.py"]
    assert 'ensure_registered_table(cursor, table_name)' in sources["lottery_dao.py"]
    assert "CREATE TABLE IF NOT EXISTS point_logs" not in combined_source
    assert "CREATE TABLE IF NOT EXISTS point_config" not in combined_source
    for table_name in POINT_GAME_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" not in combined_source
        assert f"CREATE TABLE {table_name}" not in combined_source

    assert "ALTER TABLE scratch_cards ADD COLUMN" not in combined_source
    assert "ALTER TABLE point_red_packets ADD COLUMN" not in combined_source
    assert "ALTER TABLE pk_invitations ADD COLUMN" not in combined_source
