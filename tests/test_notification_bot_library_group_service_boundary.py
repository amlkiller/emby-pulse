import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeLogger:
    def __init__(self):
        self.errors = []

    def error(self, message):
        self.errors.append(message)


class FakeDaemon:
    def __init__(self, *, fresh_by_group=None, error_on_single=None):
        self.fresh_by_group = fresh_by_group or {}
        self.error_on_single = error_on_single
        self.fresh_calls = []
        self.episode_pushes = []
        self.single_pushes = []

    def _check_fresh_episodes(self, group_id):
        self.fresh_calls.append(group_id)
        return self.fresh_by_group.get(group_id, [])

    def _push_episode_group(self, group_id, episodes):
        self.episode_pushes.append((group_id, episodes))

    def _push_single_item(self, item):
        if self.error_on_single and item.get("Id") == self.error_on_single:
            raise RuntimeError("single failed")
        self.single_pushes.append(item)


def _patch_logger(monkeypatch):
    from app.bot.notification_bot import bot_service

    logger = FakeLogger()
    monkeypatch.setattr(bot_service, "logger", logger)
    return logger


def test_library_group_groups_tv_items_by_series_and_prefers_fresh_episodes(monkeypatch):
    from app.bot.notification_bot import bot_service

    logger = _patch_logger(monkeypatch)
    fresh = [{"Id": "fresh-1", "Type": "Episode"}]
    daemon = FakeDaemon(fresh_by_group={"series-1": fresh})
    wait_calls = []

    daemon._stop_event = type("StopEvent", (), {"wait": lambda _self, seconds: wait_calls.append(seconds) or False})()
    bot_service.SystemDaemon._process_library_group(
        daemon,
        [
            {"Id": "ep-1", "Type": "Episode", "SeriesId": "series-1"},
            {"Id": "season-1", "Type": "Season", "SeriesId": "series-1"},
        ],
    )

    assert daemon.fresh_calls == ["series-1"]
    assert daemon.episode_pushes == [("series-1", fresh)]
    assert daemon.single_pushes == []
    assert wait_calls == [2]
    assert logger.errors == []


def test_library_group_falls_back_to_series_item_when_no_fresh_episodes(monkeypatch):
    from app.bot.notification_bot import bot_service

    logger = _patch_logger(monkeypatch)
    daemon = FakeDaemon()
    wait_calls = []
    daemon._stop_event = type("StopEvent", (), {"wait": lambda _self, seconds: wait_calls.append(seconds) or False})()
    series_item = {"Id": "series-1", "Type": "Series"}

    bot_service.SystemDaemon._process_library_group(daemon, [series_item])

    assert daemon.fresh_calls == ["series-1"]
    assert daemon.episode_pushes == []
    assert daemon.single_pushes == [series_item]
    assert wait_calls == [2]
    assert logger.errors == []


def test_library_group_falls_back_to_episode_only_items(monkeypatch):
    from app.bot.notification_bot import bot_service

    logger = _patch_logger(monkeypatch)
    daemon = FakeDaemon()
    wait_calls = []
    daemon._stop_event = type("StopEvent", (), {"wait": lambda _self, seconds: wait_calls.append(seconds) or False})()
    episode = {"Id": "ep-1", "Type": "Episode", "SeriesId": "series-1"}
    season = {"Id": "season-1", "Type": "Season", "SeriesId": "series-1"}

    bot_service.SystemDaemon._process_library_group(daemon, [episode, season])

    assert daemon.fresh_calls == ["series-1"]
    assert daemon.episode_pushes == [("series-1", [episode])]
    assert daemon.single_pushes == []
    assert wait_calls == [2]
    assert logger.errors == []


def test_library_group_dispatches_non_tv_item_by_id(monkeypatch):
    from app.bot.notification_bot import bot_service

    logger = _patch_logger(monkeypatch)
    daemon = FakeDaemon()
    wait_calls = []
    daemon._stop_event = type("StopEvent", (), {"wait": lambda _self, seconds: wait_calls.append(seconds) or False})()
    movie = {"Id": "movie-1", "Type": "Movie"}

    bot_service.SystemDaemon._process_library_group(daemon, [movie])

    assert daemon.fresh_calls == []
    assert daemon.episode_pushes == []
    assert daemon.single_pushes == [movie]
    assert wait_calls == [2]
    assert logger.errors == []


def test_library_group_stop_event_wait_can_end_after_first_group(monkeypatch):
    from app.bot.notification_bot import bot_service

    logger = _patch_logger(monkeypatch)
    daemon = FakeDaemon()
    wait_calls = []
    daemon._stop_event = type("StopEvent", (), {"wait": lambda _self, seconds: wait_calls.append(seconds) or True})()

    bot_service.SystemDaemon._process_library_group(
        daemon,
        [
            {"Id": "movie-1", "Type": "Movie"},
            {"Id": "movie-2", "Type": "Movie"},
        ],
    )

    assert daemon.single_pushes == [{"Id": "movie-1", "Type": "Movie"}]
    assert wait_calls == [2]
    assert logger.errors == []


def test_library_group_logs_group_errors_and_continues(monkeypatch):
    from app.bot.notification_bot import bot_service

    logger = _patch_logger(monkeypatch)
    daemon = FakeDaemon(error_on_single="movie-1")
    wait_calls = []
    daemon._stop_event = type("StopEvent", (), {"wait": lambda _self, seconds: wait_calls.append(seconds) or False})()

    bot_service.SystemDaemon._process_library_group(
        daemon,
        [
            {"Id": "movie-1", "Type": "Movie"},
            {"Id": "movie-2", "Type": "Movie"},
        ],
    )

    assert daemon.single_pushes == [{"Id": "movie-2", "Type": "Movie"}]
    assert wait_calls == [2]
    assert logger.errors == ["[入库通知] 处理失败: single failed"]
