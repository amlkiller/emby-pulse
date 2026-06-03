import ast
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


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


def test_selected_notification_callers_do_not_use_media_request_public_service_for_dao_calls():
    checked_paths = [
        _REPO_ROOT / "app/bot/notification_bot/bot_service.py",
        _REPO_ROOT / "app/bot/user_bot/user_bot_service.py",
    ]
    violations = []

    for path in checked_paths:
        rel_path = path.relative_to(_REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "app.domains.media_requests":
                    imported_names = {alias.name for alias in node.names}
                    if "public_service" in imported_names:
                        violations.append(f"{rel_path}:{node.lineno}")
                if node.module == "app.domains.media_requests.public_service":
                    imported_names = {alias.name for alias in node.names}
                    if imported_names != {"remove_gap_from_scan_state"}:
                        violations.append(f"{rel_path}:{node.lineno}")

    assert violations == []
