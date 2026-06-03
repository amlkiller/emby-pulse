import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeMediaApi:
    def __init__(self, response=None, error=None):
        self.response = response or FakeResponse()
        self.error = error
        self.calls = []

    def get(self, path, timeout=None, **kwargs):
        self.calls.append((path, timeout, kwargs))
        if self.error:
            raise self.error
        return self.response


class FakeGapDao:
    def __init__(self, *, cleared=None, error=None):
        self.cleared = set(cleared or [])
        self.error = error
        self.calls = []

    def delete_cleared_gap_record(self, series_id, season, episode):
        self.calls.append((series_id, season, episode))
        if self.error:
            raise self.error
        return (series_id, season, episode) in self.cleared


class FakeBus:
    def __init__(self):
        self.events = []

    def publish(self, event, payload):
        self.events.append((event, payload))


def _make_daemon():
    from app.bot.notification_bot import bot_service

    daemon = bot_service.SystemDaemon()
    auto_finish_calls = []
    daemon._auto_finish_request = lambda tmdb_id, season=None: auto_finish_calls.append((tmdb_id, season))
    return daemon, auto_finish_calls


def _patch_dependencies(monkeypatch, *, admin_id="admin-1", media_response=None, media_error=None, gap_cleared=None, gap_error=None):
    from app.bot.notification_bot import bot_service

    media_api = FakeMediaApi(response=media_response, error=media_error)
    gap_dao = FakeGapDao(cleared=gap_cleared, error=gap_error)
    bus = FakeBus()

    monkeypatch.setattr(bot_service, "get_admin_id", lambda: admin_id)
    monkeypatch.setattr(bot_service, "media_api", media_api)
    monkeypatch.setattr(bot_service, "gap_dao", gap_dao)
    monkeypatch.setattr(bot_service, "bus", bus)

    return media_api, gap_dao, bus


def test_push_episode_group_fetches_series_info_clears_gaps_finishes_each_added_season_and_publishes(monkeypatch):
    from app.bot.notification_bot import bot_service

    series_info = {"Id": "series-1", "Name": "Show", "ProviderIds": {"Tmdb": "123"}}
    episodes = [
        {"Id": "e-1", "ParentIndexNumber": 1, "IndexNumber": 1},
        {"Id": "e-2", "ParentIndexNumber": 1, "IndexNumber": 2},
        {"Id": "e-3", "ParentIndexNumber": 2, "IndexNumber": 1},
        {"Id": "e-missing", "ParentIndexNumber": None, "IndexNumber": 4},
    ]
    media_api, gap_dao, bus = _patch_dependencies(
        monkeypatch,
        media_response=FakeResponse(payload=series_info),
        gap_cleared={("series-1", 1, 1), ("series-1", 2, 1)},
    )
    daemon, auto_finish_calls = _make_daemon()

    daemon._push_episode_group("series-1", episodes)

    assert media_api.calls == [("/Users/admin-1/Items/series-1", 10, {})]
    assert gap_dao.calls == [("series-1", 1, 1), ("series-1", 1, 2), ("series-1", 2, 1)]
    assert set(auto_finish_calls) == {("123", 1), ("123", 2)}
    assert bus.events == [
        ("notify.gap_cleared", {"s_idx": 1, "e_idx": 1, "series_name": "Show"}),
        ("notify.gap_cleared", {"s_idx": 2, "e_idx": 1, "series_name": "Show"}),
        (
            "notify.library.new_episode",
            {"series_id": "series-1", "episodes": episodes, "series_info": series_info},
        ),
    ]


def test_push_episode_group_falls_back_to_first_episode_and_swallows_gap_errors(monkeypatch):
    fallback = {"Id": "e-1", "Name": "Episode fallback", "ProviderIds": {"Tmdb": "456"}, "ParentIndexNumber": 3, "IndexNumber": 7}
    media_api, gap_dao, bus = _patch_dependencies(
        monkeypatch,
        media_response=FakeResponse(status_code=500, payload={"Name": "ignored"}),
        gap_error=RuntimeError("gap down"),
    )
    daemon, auto_finish_calls = _make_daemon()

    daemon._push_episode_group("series-1", [fallback])

    assert media_api.calls == [("/Users/admin-1/Items/series-1", 10, {})]
    assert gap_dao.calls == [("series-1", 3, 7)]
    assert auto_finish_calls == [("456", 3)]
    assert bus.events == [
        (
            "notify.library.new_episode",
            {"series_id": "series-1", "episodes": [fallback], "series_info": fallback},
        )
    ]


def test_push_episode_group_swallows_series_fetch_errors_and_still_publishes(monkeypatch):
    fallback = {"Id": "e-1", "Name": "Episode fallback", "ParentIndexNumber": 1, "IndexNumber": 2}
    _media_api, gap_dao, bus = _patch_dependencies(
        monkeypatch,
        media_error=RuntimeError("media down"),
        gap_cleared={("series-1", 1, 2)},
    )
    daemon, auto_finish_calls = _make_daemon()

    daemon._push_episode_group("series-1", [fallback])

    assert gap_dao.calls == [("series-1", 1, 2)]
    assert auto_finish_calls == []
    assert bus.events == [
        ("notify.gap_cleared", {"s_idx": 1, "e_idx": 2, "series_name": "Episode fallback"}),
        (
            "notify.library.new_episode",
            {"series_id": "series-1", "episodes": [fallback], "series_info": fallback},
        ),
    ]


def test_push_single_item_refreshes_item_auto_finishes_and_publishes(monkeypatch):
    refreshed = {"Id": "movie-1", "Name": "Movie", "ProviderIds": {"Tmdb": "789"}}
    media_api, _gap_dao, bus = _patch_dependencies(monkeypatch, media_response=FakeResponse(payload=refreshed))
    daemon, auto_finish_calls = _make_daemon()

    daemon._push_single_item({"Id": "movie-1", "Name": "Webhook Movie"})

    assert media_api.calls == [("/Items/movie-1", 10, {})]
    assert auto_finish_calls == [("789", None)]
    assert bus.events == [("notify.library.new_item", refreshed)]


def test_push_single_item_preserves_original_item_when_refresh_fails(monkeypatch):
    original = {"Id": "movie-1", "Name": "Webhook Movie"}
    media_api, _gap_dao, bus = _patch_dependencies(monkeypatch, media_error=RuntimeError("media down"))
    daemon, auto_finish_calls = _make_daemon()

    daemon._push_single_item(original)

    assert media_api.calls == [("/Items/movie-1", 10, {})]
    assert auto_finish_calls == []
    assert bus.events == [("notify.library.new_item", original)]
