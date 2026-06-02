import inspect
import sqlite3
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _columns(conn, table_name):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def test_local_playback_store_webhook_insert_uses_registry_bootstrap(monkeypatch, tmp_path):
    from app.infra.db import local_playback_store

    db_path = tmp_path / "playback_reporting.db"
    monkeypatch.setattr(local_playback_store, "DB_PATH", str(db_path))

    local_playback_store.insert_webhook_playback_ip_record(
        user_id="u1",
        user_name="User One",
        item_id="i1",
        item_name="Movie One",
        date_created="2026-06-02 00:00:00",
        client="Web",
        device_name="Browser",
        remote_endpoint="203.0.113.10",
        location="Shanghai",
        isp="Example ISP",
    )

    with sqlite3.connect(db_path) as conn:
        assert {"RemoteEndPoint", "Location", "ISP", "ClientName", "ItemType"}.issubset(
            _columns(conn, "PlaybackActivity")
        )
        row = conn.execute(
            "SELECT UserId, ItemId, RemoteEndPoint, Location, ISP FROM PlaybackActivity"
        ).fetchone()

    assert row == ("u1", "i1", "203.0.113.10", "Shanghai", "Example ISP")


def test_local_playback_store_bot_insert_applies_item_type_to_legacy_table(monkeypatch, tmp_path):
    from app.infra.db import local_playback_store

    db_path = tmp_path / "playback_reporting.db"
    monkeypatch.setattr(local_playback_store, "DB_PATH", str(db_path))

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE PlaybackActivity (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                UserId TEXT,
                UserName TEXT,
                ItemId TEXT,
                ItemName TEXT,
                PlayDuration INTEGER,
                Client TEXT,
                DeviceName TEXT
            )
            """
        )
        conn.commit()

    local_playback_store.insert_bot_playback_history_record(
        user_id="u2",
        user_name="User Two",
        item_id="i2",
        item_name="Episode One",
        item_type="Episode",
        client="Telegram",
        device_name="Bot",
        remote_endpoint="198.51.100.5",
        location="Beijing",
        isp="Example ISP",
    )

    with sqlite3.connect(db_path) as conn:
        assert {"RemoteEndPoint", "Location", "ISP", "ClientName", "ItemType"}.issubset(
            _columns(conn, "PlaybackActivity")
        )
        row = conn.execute(
            "SELECT UserId, ItemId, ItemType, RemoteEndPoint FROM PlaybackActivity"
        ).fetchone()

    assert row == ("u2", "i2", "Episode", "198.51.100.5")


def test_local_playback_store_uses_playback_schema_bootstrap_without_local_ddl():
    from app.infra.db import local_playback_store

    source = inspect.getsource(local_playback_store)

    assert "ensure_playback_table(cursor)" in source
    assert "WEBHOOK_PLAYBACK_SCHEMA" not in source
    assert "CREATE TABLE IF NOT EXISTS PlaybackActivity" not in source
    assert "ALTER TABLE PlaybackActivity ADD COLUMN" not in source
