import datetime as real_datetime
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


class FakeDateTime:
    @classmethod
    def now(cls):
        return real_datetime.datetime(2026, 6, 3, 21, 30, 15)


class FakeDateTimeModule:
    datetime = FakeDateTime


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


class FakeMediaApi:
    def __init__(self, responses=None, error=None):
        self.responses = responses or {}
        self.error = error
        self.calls = []

    def get(self, path, timeout=None):
        self.calls.append((path, timeout))
        if self.error:
            raise self.error
        response = self.responses.get(path)
        if callable(response):
            return response(path, timeout)
        return response or FakeResponse(404, {})


class FakePlugin:
    enabled = True

    def __init__(self):
        self.calls = []

    def render(self, key, vars):
        self.calls.append((key, vars))
        return "plugin playback caption"


def _make_bot(image_resolver=None):
    from app.bot.notification_bot import bot_service

    bot = bot_service.NotificationBot()
    sent = []
    image_calls = []

    def download_image(item_id, image_type="Primary", image_tag=None):
        image_calls.append((item_id, image_type, image_tag))
        if image_resolver:
            return image_resolver(item_id, image_type, image_tag)
        return None

    bot._download_emby_image = download_image
    bot._is_muted = lambda user_id, event_type: False
    bot.send_photo = lambda chat_id, image, caption, reply_markup=None, platform="all", wecom_photo_io=None, **_kwargs: sent.append(
        (chat_id, image, caption, reply_markup, platform, wecom_photo_io)
    )
    return bot, sent, image_calls


def test_playback_event_disabled_skips_side_effects(monkeypatch):
    from app.bot.notification_bot import bot_service

    logger = FakeLogger()
    bot, sent, image_calls = _make_bot()
    bot._is_muted = lambda *_args: (_ for _ in ()).throw(AssertionError("mute should not run"))

    monkeypatch.setattr(bot_service, "get_enable_notify", lambda: False)
    monkeypatch.setattr(bot_service, "logger", logger)

    bot.on_playback_event({"Session": {"UserId": "u-1"}}, "start")

    assert sent == []
    assert image_calls == []
    assert logger.infos == ["🔇 [播放通知] 开关未开启，跳过"]
    assert logger.errors == []


def test_playback_event_muted_user_logs_and_skips_send(monkeypatch):
    from app.bot.notification_bot import bot_service

    logger = FakeLogger()
    media_api = FakeMediaApi()
    bot, sent, image_calls = _make_bot()
    bot._is_muted = lambda user_id, event_type: True

    monkeypatch.setattr(bot_service, "get_enable_notify", lambda: True)
    monkeypatch.setattr(bot_service, "media_api", media_api)
    monkeypatch.setattr(bot_service, "logger", logger)

    bot.on_playback_event(
        {
            "Session": {"UserId": "u-1"},
            "User": {"Id": "u-1", "Name": "Alice"},
            "Item": {"Id": "m-1", "Name": "Film"},
        },
        "stop",
    )

    assert sent == []
    assert image_calls == []
    assert media_api.calls == []
    assert logger.infos == [
        "🔔 [播放通知] 收到 stop 事件，用户: Alice (ID: u-1)",
        "🔇 [播放通知] 用户 Alice 被静音，跳过",
    ]
    assert logger.errors == []


def test_playback_event_default_episode_message_enriches_details_and_uses_series_jump(monkeypatch):
    from app.bot.notification_bot import bot_service

    logger = FakeLogger()
    media_api = FakeMediaApi(
        {
            "/Users/u-1/Items/e-1": FakeResponse(
                200,
                {
                    "RunTimeTicks": 1000000000,
                    "Overview": "",
                    "CommunityRating": None,
                    "SeriesId": "series-1",
                },
            ),
            "/Sessions": FakeResponse(
                200,
                [{"Id": "session-1", "PlayState": {"PositionTicks": 250000000}}],
            ),
            "/Users/u-1/Items/series-1": FakeResponse(
                200,
                {
                    "Overview": "<p>Series overview</p>",
                    "CommunityRating": 8.2,
                },
            ),
        }
    )
    bot, sent, image_calls = _make_bot(
        image_resolver=lambda item_id, image_type, _image_tag: "series-backdrop"
        if (item_id, image_type) == ("series-1", "Backdrop")
        else None
    )

    monkeypatch.setattr(bot_service, "get_enable_notify", lambda: True)
    monkeypatch.setattr(bot_service, "media_api", media_api)
    monkeypatch.setattr(bot_service, "get_location", lambda ip: "Shanghai")
    monkeypatch.setattr(bot_service, "get_media_server_main_public_or_host", lambda: "emby.example.com")
    monkeypatch.setattr(bot_service, "get_media_server_host", lambda: "fallback.example.com")
    monkeypatch.setattr(bot_service, "get_plugin", lambda plugin_name: None)
    monkeypatch.setattr(bot_service, "datetime", FakeDateTimeModule)
    monkeypatch.setattr(bot_service, "logger", logger)

    item = {
        "Id": "e-1",
        "Name": "Finale",
        "Type": "Episode",
        "SeriesName": "Show",
        "ParentIndexNumber": 2,
        "IndexNumber": 3,
        "ServerId": "server-1",
    }
    bot.on_playback_event(
        {
            "Session": {
                "Id": "session-1",
                "UserId": "u-1",
                "RemoteEndPoint": "1.2.3.4",
                "Client": "Emby Web",
                "DeviceName": "Chrome",
            },
            "User": {"Id": "u-1", "Name": "Alice"},
            "Item": item,
        },
        "start",
    )

    assert media_api.calls == [
        ("/Users/u-1/Items/e-1", 2),
        ("/Sessions", 2),
        ("/Users/u-1/Items/series-1", 2),
    ]
    assert len(sent) == 1
    chat_id, image, caption, keyboard, platform, wecom_photo_io = sent[0]
    assert chat_id == "sys_notify"
    assert image == "series-backdrop"
    assert wecom_photo_io == "series-backdrop"
    assert platform == "all"
    assert "【Alice】开始播放 剧集 Show" in caption
    assert "S02E03 Finale" in caption
    assert "评分：</b>8.2/10" in caption
    assert "进度：</b>00:00:25 / 00:01:40 (25%)" in caption
    assert "IP地址：</b>1.2.3.4 Shanghai" in caption
    assert "设备：</b>Emby Web Chrome" in caption
    assert "时间：</b>2026-06-03 21:30:15" in caption
    assert "剧情：</b>Series overview" in caption
    assert keyboard == {
        "inline_keyboard": [
            [
                {
                    "text": "🔗 跳转详情",
                    "url": "https://emby.example.com/web/index.html#!/item?id=series-1&serverId=server-1",
                }
            ]
        ]
    }
    assert image_calls == [("series-1", "Primary", None), ("series-1", "Backdrop", None)]
    assert logger.infos == ["🔔 [播放通知] 收到 start 事件，用户: Alice (ID: u-1)"]
    assert logger.errors == []


def test_playback_event_plugin_caption_receives_audio_vars_and_album_jump(monkeypatch):
    from app.bot.notification_bot import bot_service

    plugin = FakePlugin()
    media_api = FakeMediaApi({"/Users/u-2/Items/a-1": FakeResponse(200, {})})
    bot, sent, image_calls = _make_bot(image_resolver=lambda *_args: "album-primary")

    monkeypatch.setattr(bot_service, "get_enable_notify", lambda: True)
    monkeypatch.setattr(bot_service, "media_api", media_api)
    monkeypatch.setattr(bot_service, "get_location", lambda ip: "Local")
    monkeypatch.setattr(bot_service, "get_media_server_main_public_or_host", lambda: "https://emby.example.com")
    monkeypatch.setattr(bot_service, "get_media_server_host", lambda: "")
    monkeypatch.setattr(bot_service, "get_plugin", lambda plugin_name: plugin)
    monkeypatch.setattr(bot_service, "datetime", FakeDateTimeModule)

    bot.on_playback_event(
        {
            "Session": {"UserId": "u-2", "RemoteEndPoint": "5.6.7.8", "Client": "App"},
            "Item": {
                "Id": "a-1",
                "Name": "Song",
                "Type": "Audio",
                "Artists": ["Artist A", "Artist B"],
                "AlbumId": "album-1",
            },
            "PlaybackPositionTicks": 0,
            "RunTimeTicks": 0,
        },
        "stop",
    )

    assert len(sent) == 1
    assert sent[0][1] == "album-primary"
    assert sent[0][2] == "plugin playback caption"
    assert sent[0][3]["inline_keyboard"][0][0]["url"] == "https://emby.example.com/web/index.html#!/item?id=album-1&serverId="
    assert sent[0][4] == "all"
    assert image_calls == [("album-1", "Primary", None), ("album-1", "Backdrop", None)]
    assert plugin.calls[0][0] == "playback_stop"
    tpl_vars = plugin.calls[0][1]
    assert tpl_vars["username"] == "未知用户"
    assert tpl_vars["title"] == "Song - Artist A, Artist B"
    assert tpl_vars["type_cn"] == "音乐"
    assert tpl_vars["rating"] == "无"
    assert tpl_vars["progress"] == "🟢 实时流/未知总时长"
    assert tpl_vars["ip"] == "5.6.7.8"
    assert tpl_vars["location"] == "Local"
    assert tpl_vars["client"] == "App"
    assert tpl_vars["device"] == "未知设备"
    assert tpl_vars["time"] == "2026-06-03 21:30:15"
    assert tpl_vars["overview"] == "暂无简介..."


def test_playback_event_falls_back_to_item_image_then_report_cover(monkeypatch):
    from app.bot.notification_bot import bot_service

    media_api = FakeMediaApi()
    bot, sent, image_calls = _make_bot(
        image_resolver=lambda item_id, image_type, _image_tag: "item-primary"
        if (item_id, image_type) == ("m-1", "Primary")
        else None
    )

    monkeypatch.setattr(bot_service, "get_enable_notify", lambda: True)
    monkeypatch.setattr(bot_service, "media_api", media_api)
    monkeypatch.setattr(bot_service, "get_location", lambda ip: "Local")
    monkeypatch.setattr(bot_service, "get_media_server_main_public_or_host", lambda: "")
    monkeypatch.setattr(bot_service, "get_media_server_host", lambda: "")
    monkeypatch.setattr(bot_service, "get_plugin", lambda plugin_name: None)
    monkeypatch.setattr(bot_service, "REPORT_COVER_URL", "fallback-cover")

    bot.on_playback_event(
        {
            "Session": {"UserId": "u-1"},
            "Item": {"Id": "m-1", "Name": "Film", "Type": "Movie"},
        },
        "start",
    )

    assert len(sent) == 1
    assert sent[0][1] == "item-primary"
    assert sent[0][3] is None
    assert sent[0][5] == "item-primary"
    assert image_calls == [
        ("m-1", "Primary", None),
        ("m-1", "Backdrop", None),
    ]

    sent.clear()
    image_calls.clear()
    bot._download_emby_image = lambda item_id, image_type="Primary", image_tag=None: image_calls.append(
        (item_id, image_type, image_tag)
    ) or None

    bot.on_playback_event(
        {
            "Session": {"UserId": "u-1"},
            "Item": {"Id": "m-2", "Name": "Film", "Type": "Movie"},
        },
        "start",
    )

    assert sent[0][1] == "fallback-cover"
    assert sent[0][5] == "fallback-cover"


def test_playback_event_outer_errors_are_logged(monkeypatch):
    from app.bot.notification_bot import bot_service

    logger = FakeLogger()
    bot, sent, image_calls = _make_bot()
    bot.send_photo = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("send down"))

    monkeypatch.setattr(bot_service, "get_enable_notify", lambda: True)
    monkeypatch.setattr(bot_service, "media_api", FakeMediaApi())
    monkeypatch.setattr(bot_service, "get_location", lambda ip: "Local")
    monkeypatch.setattr(bot_service, "get_media_server_main_public_or_host", lambda: "")
    monkeypatch.setattr(bot_service, "get_media_server_host", lambda: "")
    monkeypatch.setattr(bot_service, "get_plugin", lambda plugin_name: None)
    monkeypatch.setattr(bot_service, "logger", logger)

    bot.on_playback_event({"Session": {"UserId": "u-1"}, "Item": {"Id": "m-1", "Name": "Film"}}, "start")

    assert sent == []
    assert image_calls == [
        ("m-1", "Primary", None),
        ("m-1", "Backdrop", None),
        ("m-1", "Primary", None),
        ("m-1", "Backdrop", None),
    ]
    assert logger.errors == ["[Bot] Playback event error: send down"]
