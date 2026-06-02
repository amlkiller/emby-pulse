import ast
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeMediaRequestDao:
    def __init__(self):
        self.calls = []

    def submit_single_media_request(self, user_id, username, tmdb_id, media_type, title, year, poster, season):
        self.calls.append(
            (
                "submit_single_media_request",
                user_id,
                username,
                tmdb_id,
                media_type,
                title,
                year,
                poster,
                season,
            )
        )
        return {"ok": True}

    def list_user_recent_requests(self, user_id, limit):
        self.calls.append(("list_user_recent_requests", user_id, limit))
        return [{"tmdb_id": 1}]

    def finish_media_requests_for_item(self, tmdb_id, season):
        self.calls.append(("finish_media_requests_for_item", tmdb_id, season))
        return ([{"title": "Movie"}], [{"user_id": "u1"}])

    def list_tg_bindings(self, user_ids):
        self.calls.append(("list_tg_bindings", user_ids))
        return {"u1": "tg1"}

    def list_pending_sync_requests(self):
        self.calls.append(("list_pending_sync_requests",))
        return [{"tmdb_id": 1}]

    def mark_sync_request_finished(self, tmdb_id, season):
        self.calls.append(("mark_sync_request_finished", tmdb_id, season))

    def update_feedback_status(self, feedback_id, status):
        self.calls.append(("update_feedback_status", feedback_id, status))

    def get_request_summary_by_tmdb(self, tmdb_id):
        self.calls.append(("get_request_summary_by_tmdb", tmdb_id))
        return {"title": "Movie"}

    def list_pending_requests_by_tmdb(self, tmdb_id):
        self.calls.append(("list_pending_requests_by_tmdb", tmdb_id))
        return [{"season": 1}]

    def update_media_request_status(self, tmdb_id, season, status, reject_reason):
        self.calls.append(("update_media_request_status", tmdb_id, season, status, reject_reason))


class FakeGapDao:
    def __init__(self):
        self.calls = []

    def delete_gap_record_by_series_episode(self, series_id, season, episode):
        self.calls.append(("delete_gap_record_by_series_episode", series_id, season, episode))

    def delete_cleared_gap_record(self, series_id, season, episode):
        self.calls.append(("delete_cleared_gap_record", series_id, season, episode))
        return True

    def add_gap_perfect_series(self, series_id, tmdb_id, series_name):
        self.calls.append(("add_gap_perfect_series", series_id, tmdb_id, series_name))

    def save_gap_scan_cache(self, results):
        self.calls.append(("save_gap_scan_cache", results))


class FakeLock:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_media_requests_public_service_delegates_and_returns(monkeypatch):
    from app.domains.media_requests import public_service

    media_request_dao = FakeMediaRequestDao()
    gap_dao = FakeGapDao()
    monkeypatch.setattr(public_service, "media_request_dao", media_request_dao)
    monkeypatch.setattr(public_service, "gap_dao", gap_dao)

    assert public_service.submit_single_media_request(
        "u1", "User", 123, "tv", "Title", "2026", "poster", 2
    ) == {"ok": True}
    assert public_service.list_user_recent_requests("u1", 5) == [{"tmdb_id": 1}]
    assert public_service.finish_media_requests_for_item(123, 2) == (
        [{"title": "Movie"}],
        [{"user_id": "u1"}],
    )
    assert public_service.list_tg_bindings(["u1"]) == {"u1": "tg1"}
    assert public_service.list_pending_sync_requests() == [{"tmdb_id": 1}]
    assert public_service.mark_sync_request_finished(123, 2) is None
    assert public_service.update_feedback_status(7, 1) is None
    assert public_service.get_request_summary_by_tmdb(123) == {"title": "Movie"}
    assert public_service.list_pending_requests_by_tmdb(123) == [{"season": 1}]
    assert public_service.update_media_request_status(123, 2, 3, "reason") is None
    assert public_service.delete_gap_record_by_series_episode("s1", 1, 2) is None
    assert public_service.delete_cleared_gap_record("s1", 1, 2) is True

    assert media_request_dao.calls == [
        ("submit_single_media_request", "u1", "User", 123, "tv", "Title", "2026", "poster", 2),
        ("list_user_recent_requests", "u1", 5),
        ("finish_media_requests_for_item", 123, 2),
        ("list_tg_bindings", ["u1"]),
        ("list_pending_sync_requests",),
        ("mark_sync_request_finished", 123, 2),
        ("update_feedback_status", 7, 1),
        ("get_request_summary_by_tmdb", 123),
        ("list_pending_requests_by_tmdb", 123),
        ("update_media_request_status", 123, 2, 3, "reason"),
    ]
    assert gap_dao.calls == [
        ("delete_gap_record_by_series_episode", "s1", 1, 2),
        ("delete_cleared_gap_record", "s1", 1, 2),
    ]


def test_remove_gap_from_scan_state_updates_results_and_cache(monkeypatch):
    from app.domains.media_requests import public_service

    gap_dao = FakeGapDao()
    scan_state = {
        "results": [
            {
                "series_id": "s1",
                "tmdb_id": 123,
                "series_name": "Series One",
                "tmdb_status": "Ended",
                "gaps": [{"season": 1, "episode": 2}],
            },
            {
                "series_id": "s2",
                "tmdb_id": 456,
                "series_name": "Series Two",
                "tmdb_status": "Continuing",
                "gaps": [{"season": 1, "episode": 3}],
            },
        ]
    }
    fake_gaps_module = SimpleNamespace(scan_state=scan_state, state_lock=FakeLock())

    monkeypatch.setattr(public_service, "gap_dao", gap_dao)
    monkeypatch.setitem(sys.modules, "app.domains.media_requests.gaps", fake_gaps_module)

    public_service.remove_gap_from_scan_state("s1", 1, 2)

    assert scan_state["results"] == [
        {
            "series_id": "s2",
            "tmdb_id": 456,
            "series_name": "Series Two",
            "tmdb_status": "Continuing",
            "gaps": [{"season": 1, "episode": 3}],
        }
    ]
    assert gap_dao.calls == [
        ("add_gap_perfect_series", "s1", 123, "Series One"),
        ("save_gap_scan_cache", scan_state["results"]),
    ]


def test_selected_notification_callers_do_not_import_private_media_request_boundaries():
    checked_paths = [
        _REPO_ROOT / "app/domains/notifications/bot_service.py",
        _REPO_ROOT / "app/domains/notifications/user_bot_service.py",
    ]
    forbidden_modules = {
        "app.domains.media_requests.media_request_dao",
        "app.domains.media_requests.gap_dao",
        "app.domains.media_requests.gaps",
    }
    violations = []

    for path in checked_paths:
        rel_path = path.relative_to(_REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module in forbidden_modules:
                    violations.append(f"{rel_path}:{node.lineno}")
                if node.module == "app.domains.media_requests":
                    imported_names = {alias.name for alias in node.names}
                    if {"media_request_dao", "gap_dao", "gaps"} & imported_names:
                        violations.append(f"{rel_path}:{node.lineno}")

    assert violations == []
