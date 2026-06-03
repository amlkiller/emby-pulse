import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeLogger:
    def __init__(self):
        self.infos = []
        self.errors = []

    def info(self, message):
        self.infos.append(message)

    def error(self, message):
        self.errors.append(message)


class FakeStopEvent:
    def __init__(self, stop_after=None):
        self.calls = []
        self.stop_after = stop_after

    def wait(self, seconds):
        self.calls.append(seconds)
        return self.stop_after is not None and len(self.calls) >= self.stop_after


class FakeMediaResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FakeMediaApi:
    def __init__(self, responses=None, error=None):
        self.responses = responses or {}
        self.error = error
        self.calls = []

    def get(self, path, params=None, timeout=None):
        self.calls.append((path, params, timeout))
        if self.error:
            raise self.error
        return FakeMediaResponse(self.responses.get((path, repr(params)), self.responses.get(path, {})))


class FakeMediaRequestDao:
    def __init__(self, rows, error=None):
        self.rows = rows
        self.error = error
        self.finished = []

    def list_pending_sync_requests(self):
        if self.error:
            raise self.error
        return self.rows

    def mark_sync_request_finished(self, tmdb_id, season=None):
        self.finished.append((tmdb_id, season))


def _make_daemon(stop_after=None):
    from app.bot.notification_bot import bot_service

    daemon = bot_service.SystemDaemon()
    daemon._stop_event = FakeStopEvent(stop_after=stop_after)
    return daemon


def _patch_dependencies(monkeypatch, *, rows, admin_id="admin-1", responses=None, media_error=None, dao_error=None):
    from app.bot.notification_bot import bot_service

    logger = FakeLogger()
    media_api = FakeMediaApi(responses=responses, error=media_error)
    media_request_dao = FakeMediaRequestDao(rows, error=dao_error)

    monkeypatch.setattr(bot_service, "logger", logger)
    monkeypatch.setattr(bot_service, "media_api", media_api)
    monkeypatch.setattr(bot_service, "media_request_dao", media_request_dao)
    monkeypatch.setattr(bot_service, "get_admin_id", lambda: admin_id)

    return logger, media_api, media_request_dao


def test_pending_sync_empty_rows_and_missing_admin_skip_side_effects(monkeypatch):
    logger, media_api, media_request_dao = _patch_dependencies(monkeypatch, rows=[])
    daemon = _make_daemon()

    daemon._sync_pending_requests()

    assert media_api.calls == []
    assert media_request_dao.finished == []
    assert logger.infos == []
    assert logger.errors == []
    assert daemon._stop_event.calls == []

    logger, media_api, media_request_dao = _patch_dependencies(
        monkeypatch,
        rows=[{"tmdb_id": "tmdb-1", "media_type": "movie", "season": None}],
        admin_id=None,
    )
    daemon = _make_daemon()

    daemon._sync_pending_requests()

    assert media_api.calls == []
    assert media_request_dao.finished == []
    assert logger.infos == []
    assert logger.errors == []
    assert daemon._stop_event.calls == []


def test_pending_sync_movie_completion_uses_existing_search_contract(monkeypatch):
    search_params = {"AnyProviderIdEquals": "tmdb.tmdb-1", "IncludeItemTypes": "Movie", "Recursive": "true"}
    logger, media_api, media_request_dao = _patch_dependencies(
        monkeypatch,
        rows=[{"tmdb_id": "tmdb-1", "media_type": "movie", "season": None}],
        responses={("/Users/admin-1/Items", repr(search_params)): {"Items": [{"Id": "movie-1"}]}},
    )
    daemon = _make_daemon()

    daemon._sync_pending_requests()

    assert media_request_dao.finished == [("tmdb-1", None)]
    assert media_api.calls == [("/Users/admin-1/Items", search_params, 5)]
    assert logger.infos == ["[入库同步] 电影已入库: tmdb_id=tmdb-1"]
    assert logger.errors == []
    assert daemon._stop_event.calls == [0.5]


def test_pending_sync_update_request_completes_when_requested_episodes_exist(monkeypatch):
    search_params = {"AnyProviderIdEquals": "tmdb.tmdb-2", "IncludeItemTypes": "Series", "Recursive": "true"}
    episode_params = {
        "ParentId": "series-1",
        "IncludeItemTypes": "Episode",
        "Recursive": "true",
        "Fields": "ParentIndexNumber,IndexNumber",
    }
    logger, media_api, media_request_dao = _patch_dependencies(
        monkeypatch,
        rows=[
            {
                "tmdb_id": "tmdb-2",
                "media_type": "tv",
                "season": 2,
                "request_type": "update",
                "episodes": "1, 2, x, 03",
            }
        ],
        responses={
            ("/Users/admin-1/Items", repr(search_params)): {"Items": [{"Id": "series-1"}]},
            ("/Users/admin-1/Items", repr(episode_params)): {
                "Items": [
                    {"ParentIndexNumber": 2, "IndexNumber": 1},
                    {"ParentIndexNumber": 2, "IndexNumber": 2},
                    {"ParentIndexNumber": 2, "IndexNumber": 3},
                    {"ParentIndexNumber": 1, "IndexNumber": 3},
                ]
            },
        },
    )
    daemon = _make_daemon()

    daemon._sync_pending_requests()

    assert media_request_dao.finished == [("tmdb-2", 2)]
    assert media_api.calls == [
        ("/Users/admin-1/Items", search_params, 5),
        ("/Users/admin-1/Items", episode_params, 5),
    ]
    assert logger.infos == ["[入库同步] 追新已入库: tmdb_id=tmdb-2, season=2, episodes=1, 2, x, 03"]
    assert logger.errors == []
    assert daemon._stop_event.calls == [0.5]


def test_pending_sync_update_request_waits_for_missing_episode(monkeypatch):
    search_params = {"AnyProviderIdEquals": "tmdb.tmdb-2", "IncludeItemTypes": "Series", "Recursive": "true"}
    episode_params = {
        "ParentId": "series-1",
        "IncludeItemTypes": "Episode",
        "Recursive": "true",
        "Fields": "ParentIndexNumber,IndexNumber",
    }
    logger, media_api, media_request_dao = _patch_dependencies(
        monkeypatch,
        rows=[
            {
                "tmdb_id": "tmdb-2",
                "media_type": "tv",
                "season": 2,
                "request_type": "update",
                "episodes": "1, 2, 3",
            }
        ],
        responses={
            ("/Users/admin-1/Items", repr(search_params)): {"Items": [{"Id": "series-1"}]},
            ("/Users/admin-1/Items", repr(episode_params)): {
                "Items": [
                    {"ParentIndexNumber": 2, "IndexNumber": 1},
                    {"ParentIndexNumber": 2, "IndexNumber": 2},
                ]
            },
        },
    )
    daemon = _make_daemon()

    daemon._sync_pending_requests()

    assert media_request_dao.finished == []
    assert media_api.calls == [
        ("/Users/admin-1/Items", search_params, 5),
        ("/Users/admin-1/Items", episode_params, 5),
    ]
    assert logger.infos == []
    assert logger.errors == []
    assert daemon._stop_event.calls == [0.5]


def test_pending_sync_new_series_completes_when_requested_season_exists(monkeypatch):
    search_params = {"AnyProviderIdEquals": "tmdb.tmdb-3", "IncludeItemTypes": "Series", "Recursive": "true"}
    season_params = {"UserId": "admin-1"}
    logger, media_api, media_request_dao = _patch_dependencies(
        monkeypatch,
        rows=[{"tmdb_id": "tmdb-3", "media_type": "tv", "season": 4}],
        responses={
            ("/Users/admin-1/Items", repr(search_params)): {"Items": [{"Id": "series-3"}]},
            ("/Shows/series-3/Seasons", repr(season_params)): {"Items": [{"IndexNumber": 1}, {"IndexNumber": 4}]},
        },
    )
    daemon = _make_daemon()

    daemon._sync_pending_requests()

    assert media_request_dao.finished == [("tmdb-3", 4)]
    assert media_api.calls == [
        ("/Users/admin-1/Items", search_params, 5),
        ("/Shows/series-3/Seasons", season_params, 5),
    ]
    assert logger.infos == ["[入库同步] 求片已入库: tmdb_id=tmdb-3, season=4"]
    assert logger.errors == []
    assert daemon._stop_event.calls == [0.5]


def test_pending_sync_stop_wait_interrupts_between_rows(monkeypatch):
    first_params = {"AnyProviderIdEquals": "tmdb.tmdb-1", "IncludeItemTypes": "Movie", "Recursive": "true"}
    second_params = {"AnyProviderIdEquals": "tmdb.tmdb-2", "IncludeItemTypes": "Movie", "Recursive": "true"}
    _logger, media_api, media_request_dao = _patch_dependencies(
        monkeypatch,
        rows=[
            {"tmdb_id": "tmdb-1", "media_type": "movie", "season": None},
            {"tmdb_id": "tmdb-2", "media_type": "movie", "season": None},
        ],
        responses={
            ("/Users/admin-1/Items", repr(first_params)): {"Items": [{"Id": "movie-1"}]},
            ("/Users/admin-1/Items", repr(second_params)): {"Items": [{"Id": "movie-2"}]},
        },
    )
    daemon = _make_daemon(stop_after=1)

    daemon._sync_pending_requests()

    assert media_request_dao.finished == [("tmdb-1", None)]
    assert media_api.calls == [("/Users/admin-1/Items", first_params, 5)]
    assert daemon._stop_event.calls == [0.5]


def test_pending_sync_outer_errors_are_logged_and_swallowed(monkeypatch):
    logger, _media_api, media_request_dao = _patch_dependencies(
        monkeypatch,
        rows=[],
        dao_error=RuntimeError("dao down"),
    )
    daemon = _make_daemon()

    daemon._sync_pending_requests()

    assert media_request_dao.finished == []
    assert logger.errors == ["[入库同步] 定时同步异常: dao down"]

    logger, _media_api, media_request_dao = _patch_dependencies(
        monkeypatch,
        rows=[{"tmdb_id": "tmdb-1", "media_type": "movie", "season": None}],
        media_error=RuntimeError("media down"),
    )
    daemon = _make_daemon()

    daemon._sync_pending_requests()

    assert media_request_dao.finished == []
    assert logger.errors == ["[入库同步] 定时同步异常: media down"]
