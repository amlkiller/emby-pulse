import datetime as real_datetime
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeLogger:
    def __init__(self):
        self.infos = []

    def info(self, message):
        self.infos.append(message)


class FakeDateTime:
    @classmethod
    def now(cls):
        return real_datetime.datetime(2026, 6, 3, 22, 0)


class FakeDateTimeModule:
    datetime = FakeDateTime


class FakePlugin:
    enabled = True

    def __init__(self):
        self.calls = []

    def render(self, key, vars):
        self.calls.append((key, vars))
        return "plugin episode caption"


def _make_bot(image_resolver=None):
    from app.domains.notifications import bot_service

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


def test_library_new_episode_disabled_skips_all_side_effects(monkeypatch):
    from app.domains.notifications import bot_service

    bot, sent, channel_calls, image_calls = _make_bot()

    monkeypatch.setattr(bot_service, "get_enable_library_notify", lambda: False)

    bot.on_library_new_episode(
        {
            "series_id": "series-1",
            "episodes": [{"Id": "e-1", "IndexNumber": 1}],
            "series_info": {"Name": "Show"},
        }
    )

    assert sent == []
    assert channel_calls == []
    assert image_calls == []


def test_library_new_episode_default_caption_groups_ranges_and_sends_all(monkeypatch):
    from app.domains.notifications import bot_service

    logger = FakeLogger()
    bot, sent, channel_calls, image_calls = _make_bot(
        image_resolver=lambda item_id, image_type, _image_tag: "primary-image"
        if (item_id, image_type) == ("series-1", "Primary")
        else "backdrop-image"
        if (item_id, image_type) == ("series-1", "Backdrop")
        else None
    )

    monkeypatch.setattr(bot_service, "get_enable_library_notify", lambda: True)
    monkeypatch.setattr(
        bot_service,
        "get_media_quality_info",
        lambda item_id: {
            "quality": "4K",
            "quality_icon": "Q",
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

    series_info = {
        "Name": "Show",
        "ProductionYear": 2026,
        "CommunityRating": 8.8,
        "Overview": "<p>Series story</p>",
        "ServerId": "server-1",
    }
    episodes = [
        {"Id": "e-1", "ParentIndexNumber": 1, "IndexNumber": 1},
        {"Id": "e-2", "ParentIndexNumber": 1, "IndexNumber": 2},
        {"Id": "e-4", "ParentIndexNumber": 1, "IndexNumber": 4},
        {"Id": "e-s2", "ParentIndexNumber": 2, "IndexNumber": 1},
    ]

    bot.on_library_new_episode({"series_id": "series-1", "episodes": episodes, "series_info": series_info})

    assert len(sent) == 1
    chat_id, image, caption, keyboard, platform, wecom_photo_io = sent[0]
    assert chat_id == "sys_notify"
    assert image == "backdrop-image"
    assert wecom_photo_io == "backdrop-image"
    assert platform == "all"
    assert "新入库 剧集 Show" in caption
    assert "S01E01-E02, E04, S02E01 (共4集)" in caption
    assert "年份：2026  |  ⭐ 评分：8.8" in caption
    assert "时间：2026-06-03 22:00" in caption
    assert "剧情简介：</b>\nSeries story" in caption
    assert keyboard == {
        "inline_keyboard": [
            [
                {
                    "text": "▶️ 立即播放",
                    "url": "https://emby.example.com/web/index.html#!/item?id=series-1&serverId=server-1",
                }
            ]
        ]
    }
    assert channel_calls == [(image, caption, keyboard, "episode", series_info)]
    assert image_calls == [("series-1", "Primary", None), ("series-1", "Backdrop", None)]
    assert logger.infos == [
        "[媒体质量] 准备获取剧集质量信息: ep_id=e-1",
        "[媒体质量] 获取结果: {'quality': '4K', 'quality_icon': 'Q', 'video_codec': 'HEVC', 'audio_codec': 'TrueHD', 'resolution': '3840x2160', 'hdr': 'HDR10'}",
    ]


def test_library_new_episode_plugin_caption_receives_quality_vars_and_single_episode_title(monkeypatch):
    from app.domains.notifications import bot_service

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

    series_info = {"Name": "Show", "Overview": "", "ServerId": "server-1"}
    episodes = [{"Id": "e-1", "ParentIndexNumber": 3, "IndexNumber": 7, "Name": "Finale"}]
    bot.on_library_new_episode({"series_id": "series-1", "episodes": episodes, "series_info": series_info})

    assert len(sent) == 1
    assert sent[0][2] == "plugin episode caption"
    assert sent[0][4] == "tg"
    assert channel_calls == []
    assert image_calls == [("series-1", "Primary", None), ("series-1", "Backdrop", None)]
    assert plugin.calls[0][0] == "library_new_episode"
    tpl_vars = plugin.calls[0][1]
    assert tpl_vars["series_name"] == "Show"
    assert tpl_vars["episode_info"] == "S03E07 Finale"
    assert tpl_vars["time"] == "2026-06-03 22:00"
    assert tpl_vars["overview"] == "暂无简介..."
    assert tpl_vars["quality"] == "1080p"
    assert tpl_vars["quality_icon"] == "Q"
    assert tpl_vars["video_codec"] == "H264"
    assert tpl_vars["audio_codec"] == "AAC"
    assert tpl_vars["resolution"] == "1920x1080"


def test_library_new_episode_tg_channel_only_skips_bot_send(monkeypatch):
    from app.domains.notifications import bot_service

    bot, sent, channel_calls, _image_calls = _make_bot(image_resolver=lambda *_args: "image-bytes")
    series_info = {"Name": "Show"}

    monkeypatch.setattr(bot_service, "get_enable_library_notify", lambda: True)
    monkeypatch.setattr(bot_service, "get_media_quality_info", lambda item_id: {})
    monkeypatch.setattr(bot_service, "get_media_server_main_public_or_host", lambda: None)
    monkeypatch.setattr(bot_service, "get_media_server_host", lambda: None)
    monkeypatch.setattr(bot_service, "get_notify_channels", lambda notify_type: ["tg_channel"])
    monkeypatch.setattr(bot_service, "get_plugin", lambda plugin_name: None)

    bot.on_library_new_episode(
        {
            "series_id": "series-1",
            "episodes": [{"Id": "e-1", "ParentIndexNumber": 1, "IndexNumber": 1}],
            "series_info": series_info,
        }
    )

    assert sent == []
    assert len(channel_calls) == 1
    assert channel_calls[0][0] == "image-bytes"
    assert channel_calls[0][2] is None
    assert channel_calls[0][3] == "episode"
    assert channel_calls[0][4] is series_info


def test_library_new_episode_uses_cover_fallback_and_wecom_platform(monkeypatch):
    from app.domains.notifications import bot_service

    bot, sent, channel_calls, image_calls = _make_bot()

    monkeypatch.setattr(bot_service, "get_enable_library_notify", lambda: True)
    monkeypatch.setattr(bot_service, "get_media_quality_info", lambda item_id: {})
    monkeypatch.setattr(bot_service, "get_media_server_main_public_or_host", lambda: "")
    monkeypatch.setattr(bot_service, "get_media_server_host", lambda: "http://emby.local")
    monkeypatch.setattr(bot_service, "get_notify_channels", lambda notify_type: ["wecom", "tg_channel"])
    monkeypatch.setattr(bot_service, "get_plugin", lambda plugin_name: None)
    monkeypatch.setattr(bot_service, "REPORT_COVER_URL", "fallback-cover")

    series_info = {"Name": "Show"}
    bot.on_library_new_episode(
        {
            "series_id": "series-2",
            "episodes": [],
            "series_info": series_info,
        }
    )

    assert len(sent) == 1
    assert sent[0][1] == "fallback-cover"
    assert sent[0][4] == "wecom"
    assert sent[0][5] == "fallback-cover"
    assert sent[0][3]["inline_keyboard"][0][0]["url"] == "http://emby.local/web/index.html#!/item?id=series-2&serverId="
    assert channel_calls[0][0] == "fallback-cover"
    assert channel_calls[0][3] == "episode"
    assert image_calls == [("series-2", "Primary", None), ("series-2", "Backdrop", None)]
