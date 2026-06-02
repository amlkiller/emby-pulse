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


def test_notification_bootstraps_create_registry_tables_and_index(monkeypatch, tmp_path):
    from app.domains.notifications import bot_service_dao, notify_admin_dao, notify_rule_dao
    from app.infra.db.schema_registry import TABLE_SCHEMAS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    bot_service_dao.ensure_request_admin_messages_table()
    notify_rule_dao.ensure_bot_notify_mutes_table()
    notify_admin_dao.ensure_notify_rules_table()

    with sqlite3.connect(db_path) as conn:
        assert {
            "id",
            "tmdb_id",
            "chat_id",
            "message_id",
            "is_caption",
            "original_text",
            "created_at",
            "updated_at",
        }.issubset(_columns(conn, "request_admin_messages"))
        assert {"user_id", "event_type", "created_at"}.issubset(_columns(conn, "bot_notify_mutes"))
        assert {
            "id",
            "notify_type",
            "notify_name",
            "channels",
            "enabled",
            "config",
            "created_at",
            "updated_at",
        }.issubset(_columns(conn, "notify_rules"))
        indexes = {
            row[1] for row in conn.execute("PRAGMA index_list(request_admin_messages)").fetchall()
        }

    assert "idx_request_admin_messages_tmdb" in indexes
    for table_name in ("request_admin_messages", "bot_notify_mutes", "notify_rules"):
        assert table_name in TABLE_SCHEMAS


def test_message_bootstraps_create_registry_tables(monkeypatch, tmp_path):
    from app.domains.notifications import message_dao
    from app.infra.db.schema_registry import TABLE_SCHEMAS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    message_dao.ensure_msg_tables()
    message_dao.ensure_mute_table()
    message_dao.ensure_announcement_tables()

    with sqlite3.connect(db_path) as conn:
        assert {
            "id",
            "user_id",
            "username",
            "user_avatar",
            "last_message",
            "last_time",
            "unread_admin",
            "unread_user",
            "created_at",
        }.issubset(_columns(conn, "msg_conversations"))
        assert {
            "id",
            "conversation_id",
            "sender_type",
            "sender_id",
            "sender_name",
            "content",
            "created_at",
        }.issubset(_columns(conn, "msg_items"))
        assert {"id", "user_id", "created_at"}.issubset(_columns(conn, "msg_notify_block"))
        assert {
            "id",
            "user_id",
            "username",
            "is_muted",
            "muted_until",
            "muted_reason",
            "muted_by",
            "muted_by_name",
            "muted_at",
            "created_at",
        }.issubset(_columns(conn, "user_mutes"))
        assert {
            "id",
            "title",
            "content",
            "is_active",
            "priority",
            "view_count",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        }.issubset(_columns(conn, "announcements"))
        assert {
            "id",
            "announcement_id",
            "user_id",
            "read_at",
        }.issubset(_columns(conn, "announcement_reads"))

    for table_name in (*message_dao.MESSAGE_TABLES, "user_mutes", *message_dao.ANNOUNCEMENT_TABLES):
        assert table_name in TABLE_SCHEMAS


def test_announcement_dao_paths_work_after_registry_bootstrap(monkeypatch, tmp_path):
    from app.domains.notifications import message_dao

    _use_temp_system_db(monkeypatch, tmp_path)

    message_dao.ensure_announcement_tables()
    announcement_id = message_dao.create_announcement(
        title="Maintenance",
        content="Window tonight",
        is_active=True,
        priority=5,
        admin_id="admin-1",
        admin_name="Admin",
    )

    announcements = message_dao.list_announcements(active_only=True)
    assert len(announcements) == 1
    assert announcements[0]["id"] == announcement_id
    assert announcements[0]["title"] == "Maintenance"

    message_dao.update_announcement_fields(
        announcement_id,
        {"title": "Updated", "priority": 7},
    )
    message_dao.increment_announcement_view_count(announcement_id)
    message_dao.mark_announcement_read(announcement_id, "user-1")

    active = message_dao.list_active_announcements_with_reads("user-1")
    assert active == [
        {
            "id": announcement_id,
            "title": "Updated",
            "content": "Window tonight",
            "view_count": 1,
            "created_at": active[0]["created_at"],
            "is_new": False,
        }
    ]


def test_selected_notification_bootstraps_use_schema_registry_instead_of_local_ddl():
    sources = {
        "bot_service_dao": (_REPO_ROOT / "app/domains/notifications/bot_service_dao.py").read_text(
            encoding="utf-8"
        ),
        "notify_rule_dao": (_REPO_ROOT / "app/domains/notifications/notify_rule_dao.py").read_text(
            encoding="utf-8"
        ),
        "notify_admin_dao": (_REPO_ROOT / "app/domains/notifications/notify_admin_dao.py").read_text(
            encoding="utf-8"
        ),
        "message_dao": (_REPO_ROOT / "app/domains/notifications/message_dao.py").read_text(
            encoding="utf-8"
        ),
    }

    assert "TABLE_SCHEMAS[\"request_admin_messages\"]" in sources["bot_service_dao"]
    assert "TABLE_SCHEMAS[\"bot_notify_mutes\"]" in sources["notify_rule_dao"]
    assert "TABLE_SCHEMAS[\"notify_rules\"]" in sources["notify_admin_dao"]
    assert "TABLE_SCHEMAS[table_name]" in sources["message_dao"]
    assert "TABLE_SCHEMAS[\"user_mutes\"]" in sources["message_dao"]
    assert "ANNOUNCEMENT_TABLES" in sources["message_dao"]
    assert "ensure_registered_table(cursor, table_name)" in sources["message_dao"]

    forbidden = {
        "bot_service_dao": ["CREATE TABLE IF NOT EXISTS request_admin_messages"],
        "notify_rule_dao": ["CREATE TABLE IF NOT EXISTS bot_notify_mutes"],
        "notify_admin_dao": ["CREATE TABLE IF NOT EXISTS notify_rules"],
        "message_dao": [
            "CREATE TABLE IF NOT EXISTS msg_conversations",
            "CREATE TABLE IF NOT EXISTS msg_items",
            "CREATE TABLE IF NOT EXISTS msg_notify_block",
            "CREATE TABLE IF NOT EXISTS user_mutes",
            "CREATE TABLE IF NOT EXISTS announcements",
            "CREATE TABLE IF NOT EXISTS announcement_reads",
        ],
    }
    for source_name, patterns in forbidden.items():
        for pattern in patterns:
            assert pattern not in sources[source_name]
