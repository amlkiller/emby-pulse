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


def test_media_feedback_bootstrap_creates_registry_table(monkeypatch, tmp_path):
    from app.domains.media_requests import media_request_dao
    from app.infra.db.schema_registry import TABLE_SCHEMAS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    media_request_dao.ensure_media_request_schema()
    media_request_dao.ensure_media_request_schema()

    with sqlite3.connect(db_path) as conn:
        columns = _columns(conn, "media_feedback")

    assert "media_feedback" in TABLE_SCHEMAS
    assert {
        "id",
        "item_name",
        "user_id",
        "username",
        "issue_type",
        "description",
        "status",
        "poster_path",
        "created_at",
    }.issubset(columns)


def test_media_feedback_bootstrap_applies_registered_poster_alter(monkeypatch, tmp_path):
    from app.domains.media_requests import media_request_dao
    from app.infra.db.schema_registry import TABLE_ALTERS

    db_path = _use_temp_system_db(monkeypatch, tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE media_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT,
                user_id TEXT,
                username TEXT,
                issue_type TEXT,
                description TEXT,
                status INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()

    media_request_dao.ensure_media_request_schema()

    with sqlite3.connect(db_path) as conn:
        assert "poster_path" in _columns(conn, "media_feedback")

    assert TABLE_ALTERS["media_feedback"] == [
        "ALTER TABLE media_feedback ADD COLUMN poster_path TEXT"
    ]


def test_media_feedback_dao_paths_work_after_registry_bootstrap(monkeypatch, tmp_path):
    from app.domains.media_requests import media_request_dao

    _use_temp_system_db(monkeypatch, tmp_path)
    media_request_dao.ensure_media_request_schema()

    feedback_id = media_request_dao.create_media_feedback(
        item_name="Example Movie",
        user_id="u1",
        username="User One",
        issue_type="subtitle",
        description="Missing subtitles",
        poster_path="/poster.jpg",
    )

    mine = media_request_dao.list_my_feedback("u1")
    all_feedback = media_request_dao.list_all_feedback()

    assert mine[0]["id"] == feedback_id
    assert mine[0]["item_name"] == "Example Movie"
    assert all_feedback[0]["username"] == "User One"

    media_request_dao.update_feedback_status(feedback_id, 1)
    assert media_request_dao.list_all_feedback()[0]["status"] == 1

    media_request_dao.update_feedback_status_batch([feedback_id], -1)
    assert media_request_dao.list_all_feedback() == []


def test_media_feedback_bootstrap_uses_registry_without_touching_high_risk_migrations():
    from app.domains.media_requests import media_request_dao

    source = inspect.getsource(media_request_dao.ensure_media_request_schema)

    assert 'ensure_registered_table(cursor, "media_feedback")' in source
    assert "CREATE TABLE IF NOT EXISTS media_feedback" not in source
    assert "ALTER TABLE media_feedback ADD COLUMN poster_path" not in source

    assert "ALTER TABLE media_requests RENAME TO media_requests_old" in source
    assert "ALTER TABLE request_users RENAME TO request_users_old" in source
