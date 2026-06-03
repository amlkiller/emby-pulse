import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeGapDao:
    def __init__(self, error=None):
        self.error = error
        self.deleted = []

    def delete_gap_record_by_series_episode(self, series_id, season, episode):
        if self.error:
            raise self.error
        self.deleted.append((series_id, season, episode))


def _make_daemon():
    from app.domains.notifications import bot_service

    return bot_service.SystemDaemon()


def _patch_dependencies(monkeypatch, *, dao_error=None, scan_error=None):
    from app.domains.notifications import bot_service

    gap_dao = FakeGapDao(error=dao_error)
    scan_calls = []

    def fake_remove_gap_from_scan_state(series_id, season, episode):
        if scan_error:
            raise scan_error
        scan_calls.append((series_id, season, episode))

    monkeypatch.setattr(bot_service, "gap_dao", gap_dao)
    monkeypatch.setattr(bot_service, "remove_gap_from_scan_state", fake_remove_gap_from_scan_state)

    return gap_dao, scan_calls


def test_gap_clear_non_episode_skips_side_effects(monkeypatch):
    gap_dao, scan_calls = _patch_dependencies(monkeypatch)
    daemon = _make_daemon()

    daemon._clear_gap_record_async({"Type": "Movie", "SeriesId": "series-1", "ParentIndexNumber": 1, "IndexNumber": 2})

    assert gap_dao.deleted == []
    assert scan_calls == []


def test_gap_clear_missing_or_invalid_episode_numbers_are_swallowed(monkeypatch):
    gap_dao, scan_calls = _patch_dependencies(monkeypatch)
    daemon = _make_daemon()

    daemon._clear_gap_record_async({"Type": "Episode", "SeriesId": "series-1", "ParentIndexNumber": -1, "IndexNumber": 2})
    daemon._clear_gap_record_async({"Type": "Episode", "SeriesId": "series-1", "ParentIndexNumber": 1, "IndexNumber": -1})
    daemon._clear_gap_record_async({"Type": "Episode", "SeriesId": "series-1", "ParentIndexNumber": "bad", "IndexNumber": 2})

    assert gap_dao.deleted == []
    assert scan_calls == []


def test_gap_clear_valid_episode_deletes_gap_and_scan_state(monkeypatch):
    gap_dao, scan_calls = _patch_dependencies(monkeypatch)
    daemon = _make_daemon()

    daemon._clear_gap_record_async({"Type": "Episode", "SeriesId": 123, "ParentIndexNumber": "2", "IndexNumber": "7"})

    assert gap_dao.deleted == [("123", 2, 7)]
    assert scan_calls == [("123", 2, 7)]


def test_gap_clear_scan_state_failure_is_swallowed_after_dao_delete(monkeypatch):
    gap_dao, scan_calls = _patch_dependencies(monkeypatch, scan_error=RuntimeError("scan down"))
    daemon = _make_daemon()

    daemon._clear_gap_record_async({"Type": "Episode", "SeriesId": "series-1", "ParentIndexNumber": 2, "IndexNumber": 7})

    assert gap_dao.deleted == [("series-1", 2, 7)]
    assert scan_calls == []


def test_gap_clear_outer_dao_failure_is_swallowed(monkeypatch):
    gap_dao, scan_calls = _patch_dependencies(monkeypatch, dao_error=RuntimeError("dao down"))
    daemon = _make_daemon()

    daemon._clear_gap_record_async({"Type": "Episode", "SeriesId": "series-1", "ParentIndexNumber": 2, "IndexNumber": 7})

    assert gap_dao.deleted == []
    assert scan_calls == []
