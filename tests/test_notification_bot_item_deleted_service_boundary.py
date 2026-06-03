import datetime as real_datetime
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


class FakeDateTime:
    @classmethod
    def now(cls):
        return real_datetime.datetime(2026, 6, 3, 20, 45)


class FakeDateTimeModule:
    datetime = FakeDateTime


class FakeTimeModule:
    def __init__(self, *values):
        self.values = list(values)

    def time(self):
        if len(self.values) == 1:
            return self.values[0]
        return self.values.pop(0)


class FakeTmdbResponse:
    def __init__(self, status_code=200, poster_path="/poster.jpg"):
        self.status_code = status_code
        self.poster_path = poster_path

    def json(self):
        return {"poster_path": self.poster_path}


class FakeTmdbClient:
    def __init__(self, api_key="tmdb-key", response=None, error=None):
        self.api_key = api_key
        self.response = response or FakeTmdbResponse()
        self.error = error
        self.movie_calls = []
        self.tv_calls = []

    def get_movie_details(self, tmdb_id, proxies=None, timeout=None):
        self.movie_calls.append((tmdb_id, proxies, timeout))
        if self.error:
            raise self.error
        return self.response

    def get_tv_details(self, tmdb_id, proxies=None, timeout=None):
        self.tv_calls.append((tmdb_id, proxies, timeout))
        if self.error:
            raise self.error
        return self.response


def _make_bot(send_target=None, image_resolver=None):
    from app.domains.notifications import bot_service

    bot = bot_service.NotificationBot()
    sent = send_target if send_target is not None else []
    image_calls = []

    def download_image(item_id, image_type="Primary", image_tag=None):
        image_calls.append((item_id, image_type, image_tag))
        if image_resolver:
            return image_resolver(item_id, image_type, image_tag)
        return None

    bot._download_emby_image = download_image
    bot.send_photo = lambda chat_id, image, text, platform="all", wecom_photo_io=None, **_kwargs: sent.append(
        (chat_id, image, text, platform, wecom_photo_io)
    )
    return bot, sent, image_calls


def test_item_deleted_disabled_and_user_deletion_skip_all_side_effects(monkeypatch):
    from app.domains.notifications import bot_service

    bot, sent, image_calls = _make_bot()

    monkeypatch.setattr(bot_service, "get_notify_item_deleted", lambda: False)
    bot.on_item_deleted({"Type": "Movie", "Id": "m-1", "Name": "Movie"})

    assert sent == []
    assert image_calls == []
    assert bot.delete_cache == {}

    monkeypatch.setattr(bot_service, "get_notify_item_deleted", lambda: True)
    bot.on_item_deleted({"Type": "User", "Id": "u-1", "Name": "Alice"})
    bot.on_item_deleted({"Type": "Movie", "Id": "m-2", "Name": "删除了用户 Alice"})

    assert sent == []
    assert image_calls == []
    assert bot.delete_cache == {}


def test_item_deleted_movie_uses_primary_image_and_preserves_cache_dedupe(monkeypatch):
    from app.domains.notifications import bot_service

    bot, sent, image_calls = _make_bot(
        image_resolver=lambda item_id, image_type, _image_tag: "primary-image"
        if (item_id, image_type) == ("m-1", "Primary")
        else "backdrop-image"
        if (item_id, image_type) == ("m-1", "Backdrop")
        else None
    )
    bot.delete_cache = {"stale": 300}

    monkeypatch.setattr(bot_service, "get_notify_item_deleted", lambda: True)
    monkeypatch.setattr(bot_service, "time", FakeTimeModule(1000, 1100))
    monkeypatch.setattr(bot_service, "datetime", FakeDateTimeModule)

    payload = {"Type": "Movie", "Id": "m-1", "Name": "Film", "ProductionYear": 2025}
    bot.on_item_deleted(payload)
    bot.on_item_deleted(payload)

    assert len(sent) == 1
    chat_id, image, text, platform, wecom_photo_io = sent[0]
    assert chat_id == "sys_notify"
    assert image == "primary-image"
    assert wecom_photo_io == "primary-image"
    assert platform == "all"
    assert "系统告警：电影被删除" in text
    assert "内容：</b>Film (2025)" in text
    assert "时间：</b>2026-06-03 20:45" in text
    assert image_calls == [("m-1", "Primary", None), ("m-1", "Backdrop", None)]
    assert bot.delete_cache == {"m-1": 1000, "Film": 1000}


def test_item_deleted_episode_uses_tmdb_tv_fallback_and_safe_proxies(monkeypatch):
    from app.domains.notifications import bot_service

    bot, sent, image_calls = _make_bot()
    tmdb = FakeTmdbClient(response=FakeTmdbResponse(200, "/series-poster.jpg"))
    proxies = {"https": "http://proxy.local:8080"}

    monkeypatch.setattr(bot_service, "get_notify_item_deleted", lambda: True)
    monkeypatch.setattr(bot_service, "time", FakeTimeModule(1000))
    monkeypatch.setattr(bot_service, "datetime", FakeDateTimeModule)
    monkeypatch.setattr(bot_service, "tmdb_client", tmdb)
    monkeypatch.setattr(bot_service, "get_safe_proxies", lambda: proxies)

    bot.on_item_deleted(
        {
            "Type": "Episode",
            "Id": "e-1",
            "Name": "Finale",
            "SeriesName": "Show",
            "ParentIndexNumber": 2,
            "IndexNumber": 3,
            "SeriesProviderIds": {"Tmdb": "tv-1"},
        }
    )

    assert len(sent) == 1
    _chat_id, image, text, _platform, _wecom_photo_io = sent[0]
    assert image == "https://image.tmdb.org/t/p/w500/series-poster.jpg"
    assert "系统告警：单集被删除" in text
    assert "内容：</b>Show S02E03 Finale" in text
    assert image_calls == [
        ("e-1", "Primary", None),
        ("e-1", "Backdrop", None),
    ]
    assert tmdb.movie_calls == []
    assert tmdb.tv_calls == [("tv-1", proxies, 5)]


def test_item_deleted_uses_series_primary_before_tmdb_and_formats_season(monkeypatch):
    from app.domains.notifications import bot_service

    bot, sent, image_calls = _make_bot(
        image_resolver=lambda item_id, image_type, _image_tag: "series-primary"
        if (item_id, image_type) == ("series-1", "Primary")
        else None
    )
    tmdb = FakeTmdbClient()

    monkeypatch.setattr(bot_service, "get_notify_item_deleted", lambda: True)
    monkeypatch.setattr(bot_service, "time", FakeTimeModule(1000))
    monkeypatch.setattr(bot_service, "datetime", FakeDateTimeModule)
    monkeypatch.setattr(bot_service, "tmdb_client", tmdb)

    bot.on_item_deleted(
        {
            "Type": "Season",
            "Id": "season-1",
            "Name": "Season Name",
            "SeriesName": "Show",
            "ParentIndexNumber": 4,
            "SeriesId": "series-1",
            "ProviderIds": {"Tmdb": "tv-1"},
        }
    )

    assert len(sent) == 1
    _chat_id, image, text, _platform, _wecom_photo_io = sent[0]
    assert image == "series-primary"
    assert "系统告警：整季被删除" in text
    assert "内容：</b>Show - 第 4 季" in text
    assert image_calls == [
        ("season-1", "Primary", None),
        ("season-1", "Backdrop", None),
        ("series-1", "Primary", None),
    ]
    assert tmdb.movie_calls == []
    assert tmdb.tv_calls == []


def test_item_deleted_tmdb_exception_falls_back_to_report_cover(monkeypatch):
    from app.domains.notifications import bot_service

    bot, sent, _image_calls = _make_bot()
    tmdb = FakeTmdbClient(error=RuntimeError("tmdb down"))

    monkeypatch.setattr(bot_service, "get_notify_item_deleted", lambda: True)
    monkeypatch.setattr(bot_service, "time", FakeTimeModule(1000))
    monkeypatch.setattr(bot_service, "datetime", FakeDateTimeModule)
    monkeypatch.setattr(bot_service, "tmdb_client", tmdb)
    monkeypatch.setattr(bot_service, "get_safe_proxies", lambda: {})
    monkeypatch.setattr(bot_service, "REPORT_COVER_URL", "fallback-cover")

    bot.on_item_deleted({"Type": "Movie", "Id": "m-1", "Name": "Film", "ProviderIds": {"Tmdb": "movie-1"}})

    assert len(sent) == 1
    assert sent[0][1] == "fallback-cover"
    assert tmdb.movie_calls == [("movie-1", {}, 5)]
    assert tmdb.tv_calls == []


def test_item_deleted_outer_assembly_errors_are_logged(monkeypatch):
    from app.domains.notifications import bot_service

    logger = FakeLogger()
    bot = bot_service.NotificationBot()
    bot.send_photo = lambda *args, **kwargs: None

    monkeypatch.setattr(bot_service, "get_notify_item_deleted", lambda: True)
    monkeypatch.setattr(bot_service, "logger", logger)

    bot.on_item_deleted(None)

    assert logger.errors == ["删除通知组装异常: 'NoneType' object has no attribute 'get'"]
