import datetime as real_datetime
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeLogger:
    def __init__(self):
        self.warnings = []
        self.errors = []

    def warning(self, message):
        self.warnings.append(message)

    def error(self, message):
        self.errors.append(message)


class FakeDateTime:
    @classmethod
    def now(cls):
        return real_datetime.datetime(2026, 6, 3, 21, 0)


class FakeDateTimeModule:
    datetime = FakeDateTime


class FakePlugin:
    enabled = True

    def __init__(self):
        self.calls = []

    def render(self, key, vars):
        self.calls.append((key, vars))
        return "plugin caption"


def _make_bot(image_resolver=None):
    from app.bot.notification_bot import bot_service

    bot = bot_service.NotificationBot()
    sent = []
    channel_calls = []
    image_calls = []

    def download_image(item_id, image_type="Primary", image_tag=None):
        image_calls.append((item_id, image_type, image_tag))
        if image_resolver:
            return image_resolver(item_id, image_type, image_tag)
        return None

    bot._download_emby_image = download_image
    bot.send_photo = lambda chat_id, image, caption, reply_markup=None, platform="all", wecom_photo_io=None, **_kwargs: sent.append(
        (chat_id, image, caption, reply_markup, platform, wecom_photo_io)
    )
    bot._notify_channels = lambda photo_io, caption, keyboard, item_type, item_info: channel_calls.append(
        (photo_io, caption, keyboard, item_type, item_info)
    )

    return bot, sent, channel_calls, image_calls


def test_library_new_item_disabled_skips_all_side_effects(monkeypatch):
    from app.bot.notification_bot import bot_service

    bot, sent, channel_calls, image_calls = _make_bot()

    monkeypatch.setattr(bot_service, "get_enable_library_notify", lambda: False)

    bot.on_library_new_item({"Id": "m-1", "Name": "Film"})

    assert sent == []
    assert channel_calls == []
    assert image_calls == []


def test_library_new_item_default_caption_sends_all_and_fans_out_to_channel(monkeypatch):
    from app.bot.notification_bot import bot_service

    logger = FakeLogger()
    bot, sent, channel_calls, image_calls = _make_bot(
        image_resolver=lambda item_id, image_type, _image_tag: "primary-image"
        if (item_id, image_type) == ("m-1", "Primary")
        else "backdrop-image"
        if (item_id, image_type) == ("m-1", "Backdrop")
        else None
    )

    monkeypatch.setattr(bot_service, "get_enable_library_notify", lambda: True)
    monkeypatch.setattr(
        bot_service,
        "get_media_quality_info",
        lambda item_id: {
            "quality": "4K",
            "quality_icon": "🎬",
            "video_codec": "HEVC",
            "audio_codec": "TrueHD",
            "resolution": "3840x2160",
            "hdr": "HDR10",
        },
    )
    monkeypatch.setattr(bot_service, "get_media_server_main_public_or_host", lambda: "emby.example.com")
    monkeypatch.setattr(bot_service, "get_media_server_host", lambda: "fallback.example.com")
    monkeypatch.setattr(bot_service, "get_notify_channels", lambda notify_type: ["tg_bot", "wecom", "tg_channel"])
    monkeypatch.setattr(bot_service, "get_plugin", lambda plugin_name: None)
    monkeypatch.setattr(bot_service, "datetime", FakeDateTimeModule)
    monkeypatch.setattr(bot_service, "logger", logger)

    item = {
        "Id": "m-1",
        "ServerId": "server-1",
        "Name": "Film",
        "ProductionYear": 2026,
        "CommunityRating": 8.5,
        "Overview": "<p>A story</p>",
        "Type": "Movie",
    }
    bot.on_library_new_item(item)

    assert len(sent) == 1
    chat_id, image, caption, keyboard, platform, wecom_photo_io = sent[0]
    assert chat_id == "sys_notify"
    assert image == "backdrop-image"
    assert wecom_photo_io == "backdrop-image"
    assert platform == "all"
    assert "新入库 电影 Film" in caption
    assert "评分：8.5 / 10" in caption
    assert "时间：2026-06-03 21:00" in caption
    assert "剧情简介：</b>\nA story" in caption
    assert keyboard == {
        "inline_keyboard": [
            [
                {
                    "text": "▶️ 立即播放",
                    "url": "https://emby.example.com/web/index.html#!/item?id=m-1&serverId=server-1",
                }
            ]
        ]
    }
    assert channel_calls == [(image, caption, keyboard, "movie", item)]
    assert image_calls == [("m-1", "Primary", None), ("m-1", "Backdrop", None)]
    assert logger.warnings == ["[入库通知] 模板渲染失败，使用默认模板: fallback"]
    assert logger.errors == []


def test_library_new_item_plugin_caption_receives_quality_vars_and_sends_tg(monkeypatch):
    from app.bot.notification_bot import bot_service

    plugin = FakePlugin()
    bot, sent, channel_calls, image_calls = _make_bot(image_resolver=lambda *_args: "image-bytes")

    monkeypatch.setattr(bot_service, "get_enable_library_notify", lambda: True)
    monkeypatch.setattr(
        bot_service,
        "get_media_quality_info",
        lambda item_id: {
            "quality": "1080p",
            "quality_icon": "Q",
            "video_codec": "H264",
            "audio_codec": "AAC",
            "resolution": "1920x1080",
            "hdr": "",
        },
    )
    monkeypatch.setattr(bot_service, "get_media_server_main_public_or_host", lambda: "https://emby.example.com")
    monkeypatch.setattr(bot_service, "get_media_server_host", lambda: "")
    monkeypatch.setattr(bot_service, "get_notify_channels", lambda notify_type: ["tg_bot"])
    monkeypatch.setattr(bot_service, "get_plugin", lambda plugin_name: plugin)
    monkeypatch.setattr(bot_service, "datetime", FakeDateTimeModule)

    bot.on_library_new_item(
        {
            "Id": "s-1",
            "Name": "Show",
            "ProductionYear": 2025,
            "CommunityRating": 9,
            "Overview": "Overview",
            "Type": "Series",
        }
    )

    assert len(sent) == 1
    assert sent[0][2] == "plugin caption"
    assert sent[0][4] == "tg"
    assert channel_calls == []
    assert image_calls == [("s-1", "Primary", None), ("s-1", "Backdrop", None)]
    assert plugin.calls[0][0] == "library_new_item"
    tpl_vars = plugin.calls[0][1]
    assert tpl_vars["name"] == "Show"
    assert tpl_vars["type_cn"] == "剧集"
    assert tpl_vars["type_icon"] == "📺"
    assert tpl_vars["time"] == "2026-06-03 21:00"
    assert tpl_vars["quality"] == "1080p"
    assert tpl_vars["quality_icon"] == "Q"
    assert tpl_vars["video_codec"] == "H264"
    assert tpl_vars["audio_codec"] == "AAC"
    assert tpl_vars["resolution"] == "1920x1080"


def test_library_new_item_tg_channel_only_skips_bot_send(monkeypatch):
    from app.bot.notification_bot import bot_service

    bot, sent, channel_calls, _image_calls = _make_bot(image_resolver=lambda *_args: "image-bytes")

    monkeypatch.setattr(bot_service, "get_enable_library_notify", lambda: True)
    monkeypatch.setattr(bot_service, "get_media_quality_info", lambda item_id: {})
    monkeypatch.setattr(bot_service, "get_media_server_main_public_or_host", lambda: None)
    monkeypatch.setattr(bot_service, "get_media_server_host", lambda: None)
    monkeypatch.setattr(bot_service, "get_notify_channels", lambda notify_type: ["tg_channel"])
    monkeypatch.setattr(bot_service, "get_plugin", lambda plugin_name: None)

    item = {"Id": "e-1", "Name": "Episode", "Type": "Episode"}
    bot.on_library_new_item(item)

    assert sent == []
    assert len(channel_calls) == 1
    assert channel_calls[0][0] == "image-bytes"
    assert channel_calls[0][2] is None
    assert channel_calls[0][3] == "episode"
    assert channel_calls[0][4] is item


def test_library_new_item_uses_cover_fallback_and_movie_item_type_default(monkeypatch):
    from app.bot.notification_bot import bot_service

    bot, sent, channel_calls, image_calls = _make_bot()

    monkeypatch.setattr(bot_service, "get_enable_library_notify", lambda: True)
    monkeypatch.setattr(bot_service, "get_media_quality_info", lambda item_id: {})
    monkeypatch.setattr(bot_service, "get_media_server_main_public_or_host", lambda: "")
    monkeypatch.setattr(bot_service, "get_media_server_host", lambda: "http://emby.local")
    monkeypatch.setattr(bot_service, "get_notify_channels", lambda notify_type: ["wecom", "tg_channel"])
    monkeypatch.setattr(bot_service, "get_plugin", lambda plugin_name: None)
    monkeypatch.setattr(bot_service, "REPORT_COVER_URL", "fallback-cover")

    item = {"Id": "m-2", "Name": "No Type"}
    bot.on_library_new_item(item)

    assert len(sent) == 1
    assert sent[0][1] == "fallback-cover"
    assert sent[0][4] == "wecom"
    assert sent[0][5] == "fallback-cover"
    assert channel_calls[0][0] == "fallback-cover"
    assert channel_calls[0][3] == "movie"
    assert image_calls == [("m-2", "Primary", None), ("m-2", "Backdrop", None)]


def test_library_new_item_outer_errors_are_logged(monkeypatch):
    from app.bot.notification_bot import bot_service

    logger = FakeLogger()
    bot, sent, channel_calls, image_calls = _make_bot()

    monkeypatch.setattr(bot_service, "get_enable_library_notify", lambda: True)
    monkeypatch.setattr(bot_service, "get_media_quality_info", lambda item_id: {})
    monkeypatch.setattr(bot_service, "get_media_server_main_public_or_host", lambda: "https://emby.example.com")
    monkeypatch.setattr(bot_service, "get_media_server_host", lambda: "")
    monkeypatch.setattr(bot_service, "get_plugin", lambda plugin_name: None)
    monkeypatch.setattr(bot_service, "logger", logger)

    bot.on_library_new_item({"Name": "Missing Id"})

    assert sent == []
    assert channel_calls == []
    assert image_calls == []
    assert logger.errors == ["[入库通知] 处理失败: 'Id'"]
